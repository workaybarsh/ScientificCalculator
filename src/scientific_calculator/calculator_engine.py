from __future__ import annotations

import ast
import cmath
import io
import math
import operator
import random
import re
import tokenize
import warnings
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction

import numpy as np
import sympy as sp
from scipy import stats
from scipy.integrate import IntegrationWarning, quad
from sympy.parsing.sympy_parser import (
    auto_symbol,
    convert_xor,
    implicit_multiplication_application,
    standard_transformations,
    stringify_expr,
)

from .cas_worker import CASWorkerError, run_cas

SAFE_TRANSFORMS = tuple(t for t in standard_transformations if t is not auto_symbol) + (
    implicit_multiplication_application,
    convert_xor,
)

# SymPy's transformations need these numeric constructors. They are bindings for
# the restricted AST interpreter below; Python eval and builtins are never used.
SAFE_GLOBALS = {
    "__builtins__": {},
    "Integer": sp.Integer,
    "Float": sp.Float,
    "Rational": sp.Rational,
    "factorial": sp.factorial,
}

_ALLOWED_EXPR_CHARS = re.compile(r"^[0-9A-Za-z+\-*/().,!\s]*$")
_TRANSFORMED_NUMBER = re.compile(
    r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$"
)
_FORBIDDEN_WORDS = {
    "lambda", "import", "from", "eval", "exec", "compile", "open", "input",
    "globals", "locals", "getattr", "setattr", "delattr", "hasattr", "vars",
    "dir", "type", "object", "class", "for", "while", "if", "else", "try",
    "except", "finally", "with", "yield", "return", "raise", "assert", "pass",
    "break", "continue", "and", "or", "not", "is", "in", "True", "False",
    "None", "help", "memoryview", "bytearray", "bytes", "str", "int", "float",
}

_ALLOWED_CALL_NAMES = frozenset({
    "Integer", "Float", "Rational", "factorial",
    "sqrt", "cbrt", "Abs", "abs", "ln", "log", "exp",
    "sin", "cos", "tan", "asin", "acos", "atan",
    "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    "nPr", "nCr", "conj", "conjugate", "re", "im", "arg", "polar",
})
_ALLOWED_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_MAX_AST_NODES = 1024
_MAX_AST_DEPTH = 64
_MAX_ADJACENT_PRODUCT_LETTERS = 64
_MAX_ABS_NUMERIC_EXPONENT = 10_000
_MAX_FACTORIAL_INPUT = 10_000
_MAX_COMBINATORIC_INPUT = 10_000
_MAX_EXPANDED_STATS_SAMPLES = 1_000_000
_MAX_EXACT_DISPLAY_DECIMAL_DIGITS = 4_096
_MAX_SUMMATION_TERMS = 1_000_000


def _truncating_integer_division(left: int, right: int) -> int:
    """Divide integers with calculator-style truncation toward zero.

    ``int(left / right)`` first converts to a binary float and silently loses
    precision beyond 2**53. Base-N results must remain exact until their
    deliberate 32-bit wrap.
    """
    if right == 0:
        raise ZeroDivisionError("division by zero")
    quotient = abs(left) // abs(right)
    return -quotient if (left < 0) ^ (right < 0) else quotient


def _decimal_digit_upper_bound(value: object) -> int:
    integer=abs(int(value))
    if integer < 10:
        return 1
    # This conservative bit-length bound avoids Python's decimal-string
    # conversion entirely (and may overestimate by at most one digit).
    return max(1,math.ceil(integer.bit_length()*math.log10(2)))


def _require_exact_display_budget(value: object) -> None:
    if not isinstance(value,sp.Basic):
        return
    digits=0
    for atom in value.atoms(sp.Rational):
        if isinstance(atom,sp.Integer):
            digits+=_decimal_digit_upper_bound(atom)
        else:
            digits+=_decimal_digit_upper_bound(atom.p)
            digits+=_decimal_digit_upper_bound(atom.q)
        if digits > _MAX_EXACT_DISPLAY_DECIMAL_DIGITS:
            raise CalculatorError("Math ERROR: kesin sonuç görüntüleme sınırını aşıyor")


def _exact_nonnegative_integer(value: object) -> int | None:
    """Return a concrete integer without coercing symbolic values."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, sp.Integer)):
            result = int(value)
            return result if result >= 0 else None
        if isinstance(value, sp.Basic) and not value.free_symbols and value.is_integer is True:
            result = int(value)
            return result if result >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None
    return None


def _estimated_factorial_digits(n: int) -> int:
    if n < 2:
        return 1
    return int(math.lgamma(n + 1) / math.log(10)) + 1


def _estimated_combinatoric_digits(n: int, r: int, *, permutation: bool) -> int:
    if r < 0 or r > n:
        return 1
    if permutation:
        logarithm = math.lgamma(n + 1) - math.lgamma(n - r + 1)
    else:
        logarithm = math.lgamma(n + 1) - math.lgamma(r + 1) - math.lgamma(n - r + 1)
    return max(1, int(logarithm / math.log(10)) + 1)


def _require_estimated_digits(digits: int) -> None:
    if digits > _MAX_EXACT_DISPLAY_DECIMAL_DIGITS:
        raise CalculatorError(
            "Math ERROR: sayısal sonuç görüntüleme sınırını aşıyor "
            "(görüntüleme aralığını aşıyor)"
        )


def _preflight_factorial(value: object) -> None:
    n = _exact_nonnegative_integer(value)
    if n is not None:
        _require_estimated_digits(_estimated_factorial_digits(n))


def _preflight_power(base: object, exponent: object) -> None:
    """Reject exact integer powers that cannot be displayed before creating them."""
    try:
        if not isinstance(base, (int, sp.Integer)) or isinstance(base, bool):
            return
        if not isinstance(exponent, (int, sp.Integer)) or isinstance(exponent, bool):
            return
        base_value, exponent_value = int(base), int(exponent)
        if base_value in {-1, 0, 1} or exponent_value == 0:
            return
        # Negative exponents create an exact Rational, whose denominator has
        # the same display cost as the corresponding positive power.
        digits = int(abs(exponent_value) * math.log10(abs(base_value))) + 1
        _require_estimated_digits(digits)
    except OverflowError:
        raise CalculatorError("Math ERROR: üs sonucu çok büyük") from None


def _constant_numeric_approx(node: ast.AST) -> float | None:
    """Return a bounded-cost numeric approximation, or None for symbolic nodes."""
    try:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return None
            if isinstance(node.value, (int, float)):
                return float(node.value)
            if isinstance(node.value, str) and _TRANSFORMED_NUMBER.fullmatch(node.value):
                return float(node.value)
            return None
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPERATORS:
            value = _constant_numeric_approx(node.operand)
            return None if value is None else _ALLOWED_UNARY_OPERATORS[type(node.op)](value)
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY_OPERATORS:
            left = _constant_numeric_approx(node.left)
            right = _constant_numeric_approx(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Pow):
                try:
                    return math.pow(left, right)
                except OverflowError:
                    return math.inf
                except ValueError:
                    # A negative base with a fractional exponent is a legitimate
                    # complex expression, not evidence of resource amplification.
                    return None
            return float(_ALLOWED_BINARY_OPERATORS[type(node.op)](left, right))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            args = [_constant_numeric_approx(arg) for arg in node.args]
            if any(value is None for value in args):
                return None
            if name in {"Integer", "Float"} and len(args) == 1:
                return float(args[0])
            if name == "Rational" and len(args) == 2 and args[1] != 0:
                return float(args[0] / args[1])
            if name == "factorial" and len(args) == 1:
                value = args[0]
                if value < 0 or not value.is_integer():
                    return None
                if value > 170:
                    return math.inf
                return float(math.factorial(int(value)))
            if name in {"nPr", "nCr"} and len(args) == 2:
                n, r = args
                if n < 0 or r < 0 or not n.is_integer() or not r.is_integer():
                    return None
                if r > n:
                    return None
                operation = math.perm if name == "nPr" else math.comb
                return float(operation(int(n), int(r)))
    except (OverflowError, ZeroDivisionError):
        return math.inf
    except (TypeError, ValueError):
        return None
    return None


def _evaluated_numeric_approx(value: object) -> float | None:
    """Return a numeric approximation after safe child evaluation.

    AST-only checks cannot see through names or harmless wrappers such as
    ``sqrt`` and ``Abs``.  This second-stage check runs before a bounded
    operation itself is invoked, while leaving genuinely symbolic operands
    untouched.
    """
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (complex, np.complexfloating)):
            real=float(value.real)
            imag=float(value.imag)
            if not math.isfinite(real) or not math.isfinite(imag):
                return math.inf
            return math.hypot(real,imag)
        if isinstance(value, (int, float, Fraction, np.number)):
            try:
                return float(value)
            except OverflowError:
                return math.inf
        if not isinstance(value, sp.Basic) or value.free_symbols:
            return None
        if value in (sp.oo, -sp.oo, sp.zoo, sp.nan):
            return math.inf
        if value.is_number is not True:
            return None
        try:
            numeric=sp.N(value,18)
            if numeric.is_finite is False:
                return math.inf
            if numeric.is_real is True:
                return float(numeric)
            as_complex=complex(numeric)
            if not math.isfinite(as_complex.real) or not math.isfinite(as_complex.imag):
                return math.inf
            return math.hypot(as_complex.real,as_complex.imag)
        except OverflowError:
            return math.inf
    except (TypeError, ValueError):
        return None


def _is_known_nonfinite(value: object) -> bool:
    """Return True only when a mathematical result is definitively non-finite."""
    try:
        if isinstance(value, sp.Basic):
            if value.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
                return True
            return value.is_finite is False
        if isinstance(value, (complex, np.complexfloating)):
            return not (math.isfinite(float(value.real)) and math.isfinite(float(value.imag)))
        if isinstance(value, (float, np.floating)):
            return not math.isfinite(float(value))
        if isinstance(value, np.number):
            return not math.isfinite(float(value))
        # Python/SymPy integers and fractions are exact and finite regardless
        # of whether conversion to a machine float would overflow.
        return False
    except (TypeError, ValueError, OverflowError):
        return True


def _require_finite_math_result(value: object, message: str = "Math ERROR: sonuç sonlu değil") -> None:
    if _is_known_nonfinite(value):
        raise CalculatorError(message)


def _finite_real_float(value: object, message: str) -> float:
    """Convert a fully numeric, finite real value without accepting symbols."""
    _require_finite_math_result(value,message)
    try:
        if isinstance(value, sp.Basic):
            if value.free_symbols or value.is_number is not True:
                raise CalculatorError(message)
            numeric=sp.N(value,30)
            if numeric.is_real is not True:
                raise CalculatorError(message)
            result=float(numeric)
        elif isinstance(value, (complex, np.complexfloating)):
            if float(value.imag) != 0:
                raise CalculatorError(message)
            result=float(value.real)
        elif isinstance(value, bool):
            raise CalculatorError(message)
        else:
            result=float(value)
    except CalculatorError:
        raise
    except (TypeError, ValueError, OverflowError) as exc:
        raise CalculatorError(message) from exc
    if not math.isfinite(result):
        raise CalculatorError(message)
    return result


class _RestrictedExpression:
    """Validate and interpret only the arithmetic AST emitted by SymPy transforms."""

    def __init__(self, bindings: dict[str, object]):
        self.bindings = bindings
        self.node_count = 0

    def validate(self, node: ast.AST, depth: int = 0) -> None:
        self.node_count += 1
        if self.node_count > _MAX_AST_NODES or depth > _MAX_AST_DEPTH:
            raise CalculatorError("Syntax ERROR: İfade çok karmaşık")

        if isinstance(node, ast.Expression):
            self.validate(node.body, depth + 1)
            return
        if isinstance(node, ast.BinOp):
            if type(node.op) not in _ALLOWED_BINARY_OPERATORS:
                raise CalculatorError("Syntax ERROR: İşleme izin verilmez")
            if isinstance(node.op, ast.Pow):
                exponent = _constant_numeric_approx(node.right)
                if exponent is not None and (
                    not math.isfinite(exponent)
                    or abs(exponent) > _MAX_ABS_NUMERIC_EXPONENT
                ):
                    raise CalculatorError("Math ERROR: Üs çok büyük")
            self.validate(node.left, depth + 1)
            self.validate(node.right, depth + 1)
            return
        if isinstance(node, ast.UnaryOp):
            if type(node.op) not in _ALLOWED_UNARY_OPERATORS:
                raise CalculatorError("Syntax ERROR: İşleme izin verilmez")
            self.validate(node.operand, depth + 1)
            return
        if isinstance(node, ast.Call):
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id not in _ALLOWED_CALL_NAMES
                or node.func.id not in self.bindings
                or not callable(self.bindings[node.func.id])
                or node.keywords
            ):
                raise CalculatorError("Syntax ERROR: Fonksiyona izin verilmez")
            if node.func.id == "factorial" and node.args:
                argument = _constant_numeric_approx(node.args[0])
                if argument is not None and (
                    not math.isfinite(argument) or argument > _MAX_FACTORIAL_INPUT
                ):
                    raise CalculatorError("Math ERROR: Faktöriyel girdisi çok büyük")
            if node.func.id in {"nPr", "nCr"}:
                for arg in node.args:
                    argument = _constant_numeric_approx(arg)
                    if argument is not None and (
                        not math.isfinite(argument)
                        or abs(argument) > _MAX_COMBINATORIC_INPUT
                    ):
                        raise CalculatorError("Math ERROR: Kombinatorik girdi çok büyük")
            for arg in node.args:
                self.validate(arg, depth + 1)
            return
        if isinstance(node, ast.Name):
            if node.id not in self.bindings or node.id == "__builtins__":
                raise CalculatorError(f"Syntax ERROR: Bilinmeyen ad: {node.id}")
            return
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or value is None or value is Ellipsis:
                raise CalculatorError("Syntax ERROR: Matematik dışı sabit")
            if isinstance(value, (int, float)):
                return
            # auto_number emits numeric strings only as arguments to Float.
            if isinstance(value, str) and _TRANSFORMED_NUMBER.fullmatch(value):
                return
            raise CalculatorError("Syntax ERROR: Matematik dışı sabit")
        # Attribute, tuple/list/dict/set, subscript, comprehensions and every
        # statement-like construct are rejected here even if a future lexical
        # normalization change accidentally makes one reachable.
        raise CalculatorError("Syntax ERROR: İfade yapısına izin verilmez")

    def evaluate(self, node: ast.AST):
        if isinstance(node, ast.Expression):
            return self.evaluate(node.body)
        if isinstance(node, ast.BinOp):
            operation = _ALLOWED_BINARY_OPERATORS[type(node.op)]
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            if isinstance(node.op, ast.Pow):
                exponent = _evaluated_numeric_approx(right)
                if exponent is not None and (
                    not math.isfinite(exponent)
                    or abs(exponent) > _MAX_ABS_NUMERIC_EXPONENT
                ):
                    raise CalculatorError("Math ERROR: Üs çok büyük")
                _preflight_power(left, right)
            return operation(left, right)
        if isinstance(node, ast.UnaryOp):
            operation = _ALLOWED_UNARY_OPERATORS[type(node.op)]
            return operation(self.evaluate(node.operand))
        if isinstance(node, ast.Call):
            function = self.bindings[node.func.id]
            args = tuple(self.evaluate(arg) for arg in node.args)
            if node.func.id == "factorial" and args:
                argument = _evaluated_numeric_approx(args[0])
                if argument is not None and (
                    not math.isfinite(argument) or argument > _MAX_FACTORIAL_INPUT
                ):
                    raise CalculatorError("Math ERROR: Faktöriyel girdisi çok büyük")
                _preflight_factorial(args[0])
            if node.func.id in {"nPr", "nCr"}:
                for arg in args:
                    argument = _evaluated_numeric_approx(arg)
                    if argument is not None and (
                        not math.isfinite(argument)
                        or abs(argument) > _MAX_COMBINATORIC_INPUT
                    ):
                        raise CalculatorError("Math ERROR: Kombinatorik girdi çok büyük")
            return function(*args)
        if isinstance(node, ast.Name):
            return self.bindings[node.id]
        if isinstance(node, ast.Constant):
            return node.value
        raise CalculatorError("Syntax ERROR: İfade yapısına izin verilmez")


class CalculatorError(Exception):
    pass


def _combinatoric(n, r, *, permutation: bool):
    """Apply calculator (not generalized SymPy) domain rules for nPr/nCr."""
    numeric_n, numeric_r = _evaluated_numeric_approx(n), _evaluated_numeric_approx(r)
    if numeric_n is not None and numeric_r is not None and (
        not math.isfinite(numeric_n) or not math.isfinite(numeric_r)
        or not numeric_n.is_integer() or not numeric_r.is_integer()
        or numeric_n < 0 or numeric_r < 0 or numeric_r > numeric_n
    ):
        raise CalculatorError("Math ERROR")
    exact_n, exact_r = _exact_nonnegative_integer(n), _exact_nonnegative_integer(r)
    if exact_n is not None and exact_r is not None:
        _require_estimated_digits(
            _estimated_combinatoric_digits(exact_n, exact_r, permutation=permutation)
        )
    if permutation:
        return sp.factorial(n) / sp.factorial(n-r)
    return sp.binomial(n, r)


# CODATA 2010 legacy constants are retained for compatibility with the original
# calculator data.  The UI labels this dataset explicitly rather than implying
# that every value is a current CODATA recommendation.
CONSTANTS_DATASET_LABEL = "CODATA 2010 legacy compatibility dataset"
CONSTANTS: dict[str, tuple[str, float]] = {
    "h": ("Planck constant", 6.62606957e-34),
    "hbar": ("Reduced Planck constant", 1.054571726e-34),
    "c0": ("Speed of light in vacuum", 299792458.0),
    "eps0": ("Vacuum electric permittivity", 8.854187817e-12),
    "mu0": ("Vacuum magnetic permeability", 1.2566370614e-6),
    "Z0": ("Characteristic impedance of vacuum", 376.730313461),
    "G": ("Newtonian gravitational constant", 6.67384e-11),
    "lP": ("Planck length", 1.616199e-35),
    "tP": ("Planck time", 5.39106e-44),
    "muN": ("Nuclear magneton", 5.05078353e-27),
    "muB": ("Bohr magneton", 9.27400968e-24),
    "qe": ("Elementary charge", 1.602176565e-19),
    "Phi0": ("Magnetic flux quantum", 2.067833758e-15),
    "G0": ("Conductance quantum", 7.7480917346e-5),
    "KJ": ("Josephson constant", 483597.870e9),
    "RK": ("von Klitzing constant", 25812.8074434),
    "mp": ("Proton mass", 1.672621777e-27),
    "mn": ("Neutron mass", 1.674927351e-27),
    "me": ("Electron mass", 9.10938291e-31),
    "mmu": ("Muon mass", 1.883531475e-28),
    "a0": ("Bohr radius", 5.2917721092e-11),
    "alpha": ("Fine-structure constant", 7.2973525698e-3),
    "re": ("Classical electron radius", 2.8179403267e-15),
    "lambdaC": ("Electron Compton wavelength", 2.4263102389e-12),
    "gamma_p": ("Proton gyromagnetic ratio", 2.67522128e8),
    "lambdaCp": ("Proton Compton wavelength", 1.32140985623e-15),
    "lambdaCn": ("Neutron Compton wavelength", 1.3195909068e-15),
    "Rinf": ("Rydberg constant", 10973731.568539),
    "mu_p": ("Proton magnetic moment", 1.410606743e-26),
    "mu_e": ("Electron magnetic moment", -9.2847643e-24),
    "mu_n": ("Neutron magnetic moment", -9.662365e-27),
    "mu_mu": ("Muon magnetic moment", -4.49044807e-26),
    "mtau": ("Tau particle mass", 3.16747e-27),
    "u": ("Unified atomic mass constant", 1.660538921e-27),
    "F": ("Faraday constant", 96485.3365),
    "NA": ("Avogadro constant", 6.02214129e23),
    "kB": ("Boltzmann constant", 1.3806488e-23),
    "Vm": ("Ideal-gas standard molar volume", 0.022710953),
    "R": ("Molar gas constant", 8.3144621),
    "c1": ("First radiation constant", 3.74177153e-16),
    "c2": ("Second radiation constant", 1.4387770e-2),
    "sigmaSB": ("Stefan–Boltzmann constant", 5.670373e-8),
    "g": ("Standard acceleration of gravity", 9.80665),
    "atm": ("Standard atmosphere", 101325.0),
    "RK90": ("Conventional von Klitzing constant", 25812.807),
    "KJ90": ("Conventional Josephson constant", 483597.9e9),
    "tC": ("Kelvin equivalent of 0 °C", 273.15),
}

# 20 bidirectional pairs = 40 conversion commands.
CONVERSIONS = {
    "in→cm": lambda x: x * 2.54, "cm→in": lambda x: x / 2.54,
    "ft→m": lambda x: x * 0.3048, "m→ft": lambda x: x / 0.3048,
    "yd→m": lambda x: x * 0.9144, "m→yd": lambda x: x / 0.9144,
    "mile→km": lambda x: x * 1.609344, "km→mile": lambda x: x / 1.609344,
    "n mile→m": lambda x: x * 1852.0, "m→n mile": lambda x: x / 1852.0,
    "pc→km": lambda x: x * 3.0856775814913673e13, "km→pc": lambda x: x / 3.0856775814913673e13,
    "acre→m²": lambda x: x * 4046.8564224, "m²→acre": lambda x: x / 4046.8564224,
    "gal(US)→L": lambda x: x * 3.785411784, "L→gal(US)": lambda x: x / 3.785411784,
    "gal(UK)→L": lambda x: x * 4.54609, "L→gal(UK)": lambda x: x / 4.54609,
    "oz→g": lambda x: x * 28.349523125, "g→oz": lambda x: x / 28.349523125,
    "lb→kg": lambda x: x * 0.45359237, "kg→lb": lambda x: x / 0.45359237,
    "km/h→m/s": lambda x: x / 3.6, "m/s→km/h": lambda x: x * 3.6,
    "atm→Pa": lambda x: x * 101325.0, "Pa→atm": lambda x: x / 101325.0,
    "mmHg→Pa": lambda x: x * 133.322387415, "Pa→mmHg": lambda x: x / 133.322387415,
    "kgf/cm²→Pa": lambda x: x * 98066.5, "Pa→kgf/cm²": lambda x: x / 98066.5,
    "lbf/in²→kPa": lambda x: x * 6.894757293168, "kPa→lbf/in²": lambda x: x / 6.894757293168,
    "kgf·m→J": lambda x: x * 9.80665, "J→kgf·m": lambda x: x / 9.80665,
    "J→cal": lambda x: x / 4.1855, "cal→J": lambda x: x * 4.1855,
    "hp→kW": lambda x: x * 0.7456998715822702, "kW→hp": lambda x: x / 0.7456998715822702,
    "°F→°C": lambda x: (x - 32) * 5 / 9, "°C→°F": lambda x: x * 9 / 5 + 32,
}


def _to_32bit(v: int) -> int:
    return v & 0xFFFFFFFF


def _signed32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


_SUPPORTED_BASES = frozenset({2, 8, 10, 16})


@dataclass
class CalculatorSettings:
    angle_unit: str = "RAD"
    input_output: str = "MathI/MathO"
    number_format: str = "Fix"
    number_digits: int = 3
    engineer_symbol: bool = False
    fraction_result: str = "d/c"
    complex_format: str = "a+bi"
    statistics_freq: bool = False
    spreadsheet_auto_calc: bool = True
    spreadsheet_show_cell: str = "Formula"
    equation_complex: bool = True
    table_two_functions: bool = False
    decimal_mark: str = "Dot"
    digit_separator: bool = False
    multiline_font: str = "Normal"


@dataclass
class ScientificCalculatorEngine:
    settings: CalculatorSettings = field(default_factory=CalculatorSettings)
    ans: sp.Expr = sp.Integer(0)
    memory: dict[str, sp.Expr] = field(default_factory=lambda: {k: sp.Integer(0) for k in "ABCDEFMxy"})
    history: list[tuple[str, str]] = field(default_factory=list)
    matrices: dict[str, np.ndarray | None] = field(default_factory=lambda: {f"Mat{x}": None for x in "ABCD"})
    mat_ans: np.ndarray | None = None
    vectors: dict[str, np.ndarray | None] = field(default_factory=lambda: {f"Vct{x}": None for x in "ABCD"})
    vct_ans: np.ndarray | None = None
    # Direct engine consumers get a bounded CAS process. The UI worker turns
    # this off so it remains the sole child process that cancellation owns.
    cas_isolated: bool = field(default=True, repr=False, compare=False)
    cas_timeout: float | None = field(default=30.0, repr=False, compare=False)

    def _run_cas(self, operation: str, payload: dict[str, object]):
        return run_cas(
            operation,
            payload,
            timeout=self.cas_timeout,
            isolated=self.cas_isolated,
        )

    def _angle_to_rad(self, x):
        if self.settings.angle_unit == "DEG": return x * sp.pi / 180
        if self.settings.angle_unit == "GRA": return x * sp.pi / 200
        return x

    def _rad_to_angle(self, x):
        if self.settings.angle_unit == "DEG": return x * 180 / sp.pi
        if self.settings.angle_unit == "GRA": return x * 200 / sp.pi
        return x

    def locals(self, extra=None):
        d = {
            "pi": sp.pi, "e": sp.E, "i": sp.I, "I": sp.I, "Ans": self.ans,
            **self.memory,
            "sqrt": sp.sqrt, "cbrt": lambda x: sp.real_root(x, 3), "Abs": sp.Abs, "abs": sp.Abs,
            "ln": sp.log, "log": lambda x, b=10: sp.log(x, b), "exp": sp.exp,
            "sin": lambda x: sp.sin(self._angle_to_rad(x)),
            "cos": lambda x: sp.cos(self._angle_to_rad(x)),
            "tan": lambda x: sp.tan(self._angle_to_rad(x)),
            "asin": lambda x: self._rad_to_angle(sp.asin(x)),
            "acos": lambda x: self._rad_to_angle(sp.acos(x)),
            "atan": lambda x: self._rad_to_angle(sp.atan(x)),
            "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
            "asinh": sp.asinh, "acosh": sp.acosh, "atanh": sp.atanh,
            "factorial": sp.factorial,
            "nPr": lambda n, r: _combinatoric(n, r, permutation=True),
            "nCr": lambda n, r: _combinatoric(n, r, permutation=False),
            "conj": sp.conjugate, "conjugate": sp.conjugate,
            "re": sp.re, "im": sp.im, "arg": lambda z: self._rad_to_angle(sp.arg(z)),
            "polar": lambda r, th: r*(sp.cos(self._angle_to_rad(th)) + sp.I*sp.sin(self._angle_to_rad(th))),
        }
        if extra:
            for name, value in extra.items():
                if len(name) != 1 or not name.isascii() or not name.isalpha():
                    raise CalculatorError("Syntax ERROR: Değişken tek harf olmalıdır")
                if isinstance(value, bool) or callable(value) or not isinstance(
                    value, (sp.Basic, int, float, complex, Fraction, np.number)
                ):
                    raise CalculatorError("Syntax ERROR: Geçersiz değişken değeri")
            d.update(extra)
        return d

    @staticmethod
    def normalize(text: str) -> str:
        t = text.strip().replace("×", "*").replace("÷", "/").replace("−", "-")
        t = t.replace("π", "pi").replace("√", "sqrt")
        t = t.replace("^", "**").replace("²", "**2").replace("³", "**3")
        t = t.replace("%", "/100")
        # The physical calculator notation permits common trig functions next
        # to their single-letter argument: ``sinxcosx`` means
        # ``sin(x)*cos(x)``.  Expand only the calculator's approved variable
        # names, so an arbitrary longer identifier never becomes a function.
        t = re.sub(r"(sin|cos|tan)([A-FMxy])", r"\1(\2)", t)
        t = re.sub(r"(sin|cos|tan)(pi)\b", r"\1(\2)", t)
        # Polar complex input r∠theta (simple numeric/expression operands).
        if "∠" in t:
            left, right = t.split("∠", 1)
            t = f"polar(({left}),({right}))"
        return t

    def _safe_parse(self, text: str, local_dict: dict[str, object]) -> sp.Expr:
        normalized = self.normalize(text)
        if not normalized.strip():
            raise CalculatorError("Syntax ERROR: Boş ifade")
        if len(normalized) > 2048:
            raise CalculatorError("Syntax ERROR: İfade çok uzun")
        if not _ALLOWED_EXPR_CHARS.fullmatch(normalized):
            raise CalculatorError("Syntax ERROR: Matematik dışı karakter")
        if "__" in normalized or "//" in normalized:
            raise CalculatorError("Syntax ERROR: Geçersiz ifade")
        parenthesis_depth = 0
        for character in normalized:
            if character == "(":
                parenthesis_depth += 1
            elif character == ")":
                parenthesis_depth -= 1
                if parenthesis_depth < 0:
                    raise CalculatorError("Syntax ERROR: unmatched closing parenthesis")
        if parenthesis_depth:
            raise CalculatorError("Syntax ERROR: unmatched opening parenthesis")
        # Block attribute access (x.real, func.__class__, etc.) while preserving decimal points.
        if re.search(r"(?:[A-Za-z][A-Za-z0-9]*|\))\s*\.", normalized):
            raise CalculatorError("Syntax ERROR: Özellik erişimine izin verilmez")

        safe_locals = dict(local_dict)
        product_letters = {
            name
            for name, value in safe_locals.items()
            if len(name) == 1
            and name.isascii()
            and name.isalpha()
            and not callable(value)
        }
        try:
            tokens = tokenize.generate_tokens(io.StringIO(normalized).readline)
            names = [tok.string for tok in tokens if tok.type == tokenize.NAME]
        except (tokenize.TokenError, IndentationError) as exc:
            raise CalculatorError("Syntax ERROR: Geçersiz ifade") from exc

        for name in names:
            if name in _FORBIDDEN_WORDS:
                raise CalculatorError("Syntax ERROR: Matematik dışı ifade")
            if name in safe_locals:
                continue
            # Equation/SOLVE/Table/Sum variables are intentionally limited to simple
            # single-letter symbols. Longer names must be an explicitly whitelisted
            # calculator function or constant.
            if len(name) == 1 and name.isascii() and name.isalpha():
                safe_locals[name] = sp.Symbol(name)
                continue
            if len(name) > 1 and all(char in product_letters for char in name):
                if len(name) > _MAX_ADJACENT_PRODUCT_LETTERS:
                    raise CalculatorError("Syntax ERROR: Bitişik çarpım ifadesi çok karmaşık")
                product=sp.Integer(1)
                for char in name:
                    product*=safe_locals[char]
                safe_locals[name]=product
                continue
            raise CalculatorError(f"Syntax ERROR: Bilinmeyen ad: {name}")

        try:
            transformed = stringify_expr(
                normalized,
                local_dict=safe_locals,
                global_dict=SAFE_GLOBALS,
                transformations=SAFE_TRANSFORMS,
            )
            syntax_tree = ast.parse(transformed, mode="eval")
            bindings = {k: v for k, v in SAFE_GLOBALS.items() if k != "__builtins__"}
            bindings.update(safe_locals)
            # Numeric constructors are emitted by the trusted transformations and
            # may not be replaced by caller-provided locals.
            for name in ("Integer", "Float", "Rational"):
                bindings[name] = SAFE_GLOBALS[name]
            restricted = _RestrictedExpression(bindings)
            restricted.validate(syntax_tree)
            result = restricted.evaluate(syntax_tree)
            if callable(result) or isinstance(result, (tuple, list, dict, set)):
                raise CalculatorError("Syntax ERROR: Matematiksel ifade bekleniyor")
            if not isinstance(result, sp.Basic):
                result = sp.sympify(result)
            if not isinstance(result, sp.Basic):
                raise CalculatorError("Syntax ERROR: Matematiksel ifade bekleniyor")
            return result
        except CalculatorError:
            raise
        except Exception as exc:
            raise CalculatorError(f"Syntax ERROR: {exc}") from exc

    def parse(self, text: str, extra=None) -> sp.Expr:
        return self._safe_parse(text, self.locals(extra))

    def symbolic_locals(self, extra=None):
        """CAS işlemleri için trigonometrik fonksiyonları standart radyan değişkeniyle yorumlar."""
        d = self.locals(extra)
        d.update({
            "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
            "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
            "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
            "asinh": sp.asinh, "acosh": sp.acosh, "atanh": sp.atanh,
            "ln": sp.log, "log": lambda x, b=10: sp.log(x, b), "exp": sp.exp,
        })
        return d

    def parse_symbolic(self, text: str, extra=None) -> sp.Expr:
        return self._safe_parse(text, self.symbolic_locals(extra))

    def equation_symbols(self, equation: str, adjacent_letters=None):
        """Bellek değerlerine bakmadan denklemde yazılı değişkenleri bulur."""
        approved_adjacent=set(self.memory)
        for name in adjacent_letters or ():
            if isinstance(name,str) and len(name)==1 and name.isascii() and name.isalpha():
                approved_adjacent.add(name)
        names=set()
        try:
            tokens=tokenize.generate_tokens(io.StringIO(self.normalize(equation)).readline)
            for token in tokens:
                if token.type != tokenize.NAME:
                    continue
                name=token.string
                if len(name)==1 and name.isascii() and name.isalpha():
                    names.add(name)
                elif len(name)>1 and all(char in approved_adjacent for char in name):
                    names.update(name)
        except (tokenize.TokenError,IndentationError):
            names.update(re.findall(r"(?<![A-Za-z_])[A-Za-z](?![A-Za-z_])",equation))
        # e, i gibi matematik sabitlerini değişken sayma. pi zaten iki harfli.
        names.difference_update({"e", "i", "I"})
        # Hesap makinesi bellek değişkenlerine öncelik ver; diğer tek harfleri de koru.
        symbols = {name: sp.Symbol(name) for name in names}
        parts = equation.split("=", 1)
        found = set()
        for part in parts:
            if not part.strip():
                continue
            try:
                expr = self.parse_symbolic(part, symbols)
                found.update(str(x) for x in expr.free_symbols)
            except CalculatorError:
                # Asıl SOLVE çağrısı daha açıklayıcı syntax hatasını üretecek.
                found.update(names)
        return sorted(found)

    def _remember_history(self, expression: str, result: str) -> None:
        self.history.append((str(expression), str(result)))
        del self.history[:-10]

    def evaluate(self, text: str, exact: bool = True):
        parts = [p.strip() for p in text.split(":") if p.strip()]
        if not parts: raise CalculatorError("Syntax ERROR")
        outputs = []
        pending_history = []
        # Ans must remain the value before the complete multi-expression
        # operation. Commit both it and history only once all parts succeed.
        saved_ans = self.ans
        try:
            for part in parts:
                if "=" in part:
                    raise CalculatorError("Denklem için SOLVE kullanın; kırmızı = yalnız denklem girdisidir.")
                expr = self.parse(part)
                if exact and self.settings.input_output in ("MathI/MathO", "LineI/LineO"):
                    val = sp.simplify(expr)
                else:
                    val = sp.N(expr, 15)
                _require_finite_math_result(val)
                pending_history.append((part, self.format_result(val, approximate=not exact)))
                outputs.append(val)
                # Later colon-separated expressions can intentionally use
                # Ans, but history remains transactional until final commit.
                self.ans = val
        except Exception:
            self.ans = saved_ans
            raise
        self.ans = outputs[-1]
        self.history.extend(pending_history)
        del self.history[:-10]
        return outputs[-1]

    def evaluate_with_values(self, text: str, values: dict[str, float]):
        extra = {k: sp.Float(v) for k, v in values.items()}
        expr = self.parse(text.split("=",1)[0] if "=" in text else text, extra)
        val = sp.N(expr, 15)
        _require_finite_math_result(val)
        for k,v in values.items():
            if k in self.memory: self.memory[k] = sp.Float(v)
        self.ans = val
        self._remember_history(text, self.format_result(val, approximate=True))
        return val

    def solve(self, equation: str, variable="x", guess=0.0, known_values=None):
        known_values = known_values or {}
        var = sp.Symbol(variable)
        guess_value = _finite_real_float(guess,"Cannot Solve: başlangıç tahmini sonlu reel olmalıdır")
        # Bütün denklem değişkenlerini önce sembol olarak tut; yalnız bilinenleri sonradan sayıya çevir.
        symbol_names = self.equation_symbols(
            equation,{variable,*known_values.keys()}
        )
        symbol_map = {name: sp.Symbol(name) for name in symbol_names}
        symbol_map[variable] = var
        if "=" in equation:
            l, r = equation.split("=", 1)
            f = self.parse_symbolic(l, symbol_map) - self.parse_symbolic(r, symbol_map)
        else:
            f = self.parse_symbolic(equation, symbol_map)
        if known_values:
            f = f.subs({sp.Symbol(k): sp.Float(v) for k, v in known_values.items()})
        leftovers = sorted((s for s in f.free_symbols if s != var), key=lambda z: str(z))
        if leftovers:
            raise CalculatorError("Variable ERROR: Bilinen değer girilmeli: " + ", ".join(map(str, leftovers)))
        _require_finite_math_result(f,"Cannot Solve: denklem tanımsız")
        try:
            root = self._run_cas("nsolve", {"expression": f, "symbol": var, "guess": guess_value,
                                       "tol": 1e-14, "maxsteps": 100, "prec": 40})
        except CASWorkerError:
            # nsolve başlangıç tahmininde zorlanırsa cebirsel çözümler arasından tahmine en yakın reel kökü seç.
            try:
                sols = self._run_cas("solve", {"expression": f, "symbol": var})
                real_sols = []
                for sol in sols:
                    n = complex(sp.N(sol, 30))
                    if abs(n.imag) < 1e-10:
                        real_sols.append((abs(n.real - guess_value), n.real))
                if not real_sols:
                    raise ValueError
                root = sp.Float(min(real_sols)[1], 30)
            except Exception as exc:
                raise CalculatorError("Cannot Solve: Başlangıç tahminini değiştirin") from exc
        root_value = _finite_real_float(root,"Cannot Solve: sonlu reel kök bulunamadı")
        residual = sp.N(f.subs(var, root),40)
        _finite_real_float(residual,"Cannot Solve: kök doğrulanamadı")
        if residual != 0:
            slope=sp.N(sp.diff(f,var).subs(var,root),40)
            slope_value=_finite_real_float(slope,"Cannot Solve: kök doğrulanamadı")
            if slope_value == 0:
                raise CalculatorError("Cannot Solve: kök doğrulanamadı")
            correction=sp.N(residual/slope,40)
            correction_value=abs(_finite_real_float(correction,"Cannot Solve: kök doğrulanamadı"))
            if correction_value > 1e-10*max(1.0,abs(root_value)):
                raise CalculatorError("Cannot Solve: kök doğrulanamadı")
        if variable in self.memory:
            self.memory[variable] = root
        self.ans = root
        residual_value=float(sp.re(residual))
        self._remember_history(
            f"solve {equation} for {variable}",
            f"{variable}={root_value:.12g}; L-R={residual_value:.4g}",
        )
        return root_value, residual_value

    def definite_integral(self, integrand, lower, upper, variable="x", tol=1e-10):
        """Belirli integral: kesin sonuç mümkünse onu kullan, değilse sayısal hesapla."""
        x = sp.Symbol(variable)
        expr = self.parse(integrand, {variable: x})
        lo_expr = self.parse(lower)
        hi_expr = self.parse(upper)

        # Exact-first: pi/e sınırlarında ve trigonometrik çarpımlarda kayan nokta
        # artıklarını önler. Mevcut açı modu expr içine zaten yansıtılmıştır.
        try:
            exact = self._run_cas("definite_integral", {"expression": expr, "symbol": x,
                                                    "lower": lo_expr, "upper": hi_expr})
            if not isinstance(exact, sp.Integral):
                if isinstance(exact,sp.Basic) and exact.free_symbols:
                    raise CalculatorError("Math ERROR: integral sayısal sonuç vermedi")
                result=_finite_real_float(exact,"Math ERROR: integral sonlu reel değil")
                self.ans = sp.Float(result)
                self._remember_history(
                    f"∫{lower}→{upper} {integrand} d{variable}", self.format_result(result, approximate=True)
                )
                return result
        except CalculatorError:
            raise
        except Exception:
            pass

        try:
            lo = _finite_real_float(lo_expr,"Math ERROR: integral sınırları sonlu reel olmalıdır")
            hi = _finite_real_float(hi_expr,"Math ERROR: integral sınırları sonlu reel olmalıdır")
            if expr.free_symbols - {x}:
                raise CalculatorError("Math ERROR: integralde bilinmeyen değişken var")
            # Endpoint singularities are allowed only when the one-sided limit
            # from inside the interval is finite and real (removable and
            # convergent improper endpoints remain supported).
            direction = 1 if hi >= lo else -1
            for bound_expr, side in ((lo_expr,"+" if direction>0 else "-"),(hi_expr,"-" if direction>0 else "+")):
                endpoint=sp.simplify(expr.subs(x,bound_expr))
                if _is_known_nonfinite(endpoint):
                    endpoint=sp.limit(expr,x,bound_expr,dir=side)
                _finite_real_float(endpoint,"Math ERROR: integral tanım aralığında sonlu reel değil")
            # For explicitly enumerable interior singularities, only removable
            # holes with finite real one-sided limits may reach the quadrature.
            try:
                singular_set=sp.singularities(expr,x)
            except Exception:
                singular_set=sp.S.EmptySet
            if isinstance(singular_set,sp.FiniteSet):
                low,high=sorted((lo,hi))
                for point in singular_set:
                    try: point_value=_finite_real_float(point,"Math ERROR")
                    except CalculatorError: continue
                    if low < point_value < high:
                        left_limit=sp.limit(expr,x,point,dir="-")
                        right_limit=sp.limit(expr,x,point,dir="+")
                        _finite_real_float(left_limit,"Math ERROR: integral iç tekilliği yakınsak değil")
                        _finite_real_float(right_limit,"Math ERROR: integral iç tekilliği yakınsak değil")
            fn = sp.lambdify(x, expr, modules=["numpy", "math"])
            with warnings.catch_warnings():
                warnings.simplefilter("error",IntegrationWarning)
                warnings.simplefilter("error",RuntimeWarning)
                result,error = quad(fn, lo, hi, epsabs=tol, epsrel=tol, limit=300)
            result=_finite_real_float(result,"Math ERROR: integral sonucu sonlu reel değil")
            if not math.isfinite(float(error)):
                raise CalculatorError("Math ERROR: integral hata tahmini sonlu değil")
        except CalculatorError:
            raise
        except Exception as exc:
            raise CalculatorError("Math ERROR: integral could not be evaluated") from exc
        self.ans = sp.Float(result)
        self._remember_history(
            f"∫{lower}→{upper} {integrand} d{variable}", self.format_result(result, approximate=True)
        )
        return result

    def symbolic_integral(self, integrand, variable="x"):
        x = sp.Symbol(variable)
        expr = self.parse_symbolic(integrand, {variable: x})
        try:
            result = self._run_cas("indefinite_integral", {"expression": expr, "symbol": x})
        except Exception as exc:
            raise CalculatorError("Math ERROR: sembolik integral alınamadı") from exc
        if isinstance(result, sp.Integral):
            raise CalculatorError("Math ERROR: integral kapalı biçimde bulunamadı")
        result=sp.simplify(result)
        self.ans = result
        self._remember_history(f"∫ {integrand} d{variable}", f"{self.format_result(result)} + C")
        return result

    def symbolic_derivative(self, expression, variable="x"):
        x = sp.Symbol(variable)
        expr = self.parse_symbolic(expression, {variable: x})
        try:
            result = sp.diff(expr, x)
        except Exception as exc:
            raise CalculatorError("Math ERROR: sembolik türev alınamadı") from exc
        result=sp.simplify(result)
        self.ans = result
        self._remember_history(f"d/d{variable} {expression}", self.format_result(result))
        return result

    def derivative(self, expression, point, variable="x", tol=1e-10):
        # Noktasal türev, mevcut açı birimini koruyan sayısal hesaplamadır.
        x = sp.Symbol(variable)
        expr = self.parse(expression, {variable: x})
        point_expr=self.parse(point)
        a = _finite_real_float(point_expr,"Math ERROR: türev noktası sonlu reel olmalıdır")
        try:
            exact_at=sp.simplify(sp.diff(expr,x).subs(x,point_expr))
            if isinstance(exact_at,sp.Basic) and exact_at.is_number is True:
                result=_finite_real_float(exact_at,"Math ERROR: türev bu noktada sonlu reel değil")
                self.ans=sp.Float(result)
                self._remember_history(
                    f"d/d{variable} {expression} | {variable}={point}", self.format_result(result, approximate=True)
                )
                return result
        except CalculatorError:
            raise
        except Exception:
            pass
        h = max(1e-6, abs(a) * 1e-6)
        fn = sp.lambdify(x, expr, modules=["math"])
        try:
            _finite_real_float(fn(a),"Math ERROR: fonksiyon türev noktasında tanımsız")
            left=_finite_real_float(fn(a-h),"Math ERROR: türev örneklemi sonlu reel değil")
            right=_finite_real_float(fn(a+h),"Math ERROR: türev örneklemi sonlu reel değil")
            result=_finite_real_float((right-left)/(2*h),"Math ERROR: türev sonucu sonlu reel değil")
        except CalculatorError:
            raise
        except Exception as exc:
            raise CalculatorError("Math ERROR: derivative could not be evaluated") from exc
        self.ans = sp.Float(result)
        self._remember_history(
            f"d/d{variable} {expression} | {variable}={point}", self.format_result(result, approximate=True)
        )
        return result

    def summation(self, expression, lower, upper, variable="x"):
        lower_value=self.parse(lower); upper_value=self.parse(upper)
        a=int(lower_value); b=int(upper_value)
        if a!=lower_value or b!=upper_value: raise CalculatorError("Argument ERROR: Σ sınırları tam sayı olmalıdır")
        x=sp.Symbol(variable); expr=self.parse(expression,{variable:x})
        if max(0,b-a+1)>_MAX_SUMMATION_TERMS and not expr.is_polynomial(x):
            raise CalculatorError("Math ERROR: Σ aralığı hesaplama sınırını aşıyor")
        try:
            val=self._run_cas("summation", {"expression":expr,"symbol":x,"lower":a,"upper":b})
        except CASWorkerError as exc:
            raise CalculatorError("Math ERROR: Σ hesaplanamadı") from exc
        self.ans=val
        self._remember_history(f"Σ {expression}, {variable}={lower}..{upper}", self.format_result(val))
        return val

    def pol(self, x, y):
        r=math.hypot(x,y); th=math.atan2(y,x)
        if self.settings.angle_unit=="DEG": th=math.degrees(th)
        elif self.settings.angle_unit=="GRA": th=th*200/math.pi
        return r,th

    def rec(self, r, theta):
        if self.settings.angle_unit=="DEG": theta=math.radians(theta)
        elif self.settings.angle_unit=="GRA": theta=theta*math.pi/200
        return r*math.cos(theta), r*math.sin(theta)

    def dms_from_decimal(self, x):
        sign=-1 if x<0 else 1; x=abs(x); d=int(x); m=int((x-d)*60); s=((x-d)*60-m)*60
        # Keep the sign even for values whose degree component is zero, such as
        # -0.5° -> -0° 30′ 0″.  A signed zero lets decimal_from_dms round-trip it.
        return math.copysign(float(d), sign),m,s

    def decimal_from_dms(self,d,m,s):
        sign=-1 if d<0 or (d==0 and math.copysign(1.0, float(d))<0) else 1
        return sign*(abs(d)+m/60+s/3600)

    def prime_factorization(self, n: object):
        """Factor a finite positive integer without silently truncating input."""
        try:
            value = self.parse(n) if isinstance(n, str) else sp.sympify(n)
        except Exception as exc:
            raise CalculatorError("Math ERROR: FACT requires a positive integer") from exc
        if (
            not isinstance(value, sp.Basic)
            or value.free_symbols
            or value.is_finite is not True
            or value.is_integer is not True
        ):
            raise CalculatorError("Math ERROR: FACT requires a positive integer")
        integer = int(value)
        if integer <= 0 or integer >= 10**10:
            raise CalculatorError("Math ERROR: FACT requires a positive integer of at most 10 digits")
        return sp.factorint(integer)

    def random_number(self): return random.randint(0,999)/1000.0
    def random_int(self, a: object, b: object):
        try:
            lower = self.parse(a) if isinstance(a, str) else sp.sympify(a)
            upper = self.parse(b) if isinstance(b, str) else sp.sympify(b)
            if any(
                not isinstance(value, sp.Basic)
                or value.free_symbols
                or value.is_finite is not True
                or value.is_integer is not True
                for value in (lower, upper)
            ):
                raise ValueError("integer bounds required")
            lower, upper = int(lower), int(upper)
        except Exception as exc:
            raise CalculatorError("Argument ERROR: RanInt bounds must be finite integers") from exc
        if lower > upper:
            raise CalculatorError("Argument ERROR: lower bound exceeds upper bound")
        return random.randint(lower, upper)

    def store(self,name,value=None):
        if name not in self.memory: raise CalculatorError("Argument ERROR: Geçersiz bellek")
        if value is None:
            stored = self.ans
        else:
            try:
                stored = self.parse(value) if isinstance(value, str) else sp.sympify(value)
            except CalculatorError:
                raise
            except Exception as exc:
                raise CalculatorError("Memory ERROR: invalid memory value") from exc
        self.memory[name] = stored
        return stored
    def m_plus(self): self.memory["M"] = sp.N(self.memory["M"] + self.ans); return self.memory["M"]
    def m_minus(self): self.memory["M"] = sp.N(self.memory["M"] - self.ans); return self.memory["M"]
    def reset_memory(self):
        self.ans=sp.Integer(0)
        for k in self.memory: self.memory[k]=sp.Integer(0)
    def initialize_all(self):
        self.settings=CalculatorSettings(); self.reset_memory(); self.history.clear()
        self.matrices={f"Mat{x}":None for x in "ABCD"}; self.mat_ans=None
        self.vectors={f"Vct{x}":None for x in "ABCD"}; self.vct_ans=None

    # Complex
    def complex_eval(self,text):
        v=sp.N(self.parse(text),15)
        _require_finite_math_result(v)
        self.ans=v
        return v
    def complex_argument(self,z):
        z=complex(z); a=cmath.phase(z)
        if self.settings.angle_unit=="DEG": a=math.degrees(a)
        elif self.settings.angle_unit=="GRA": a=a*200/math.pi
        return a
    def to_polar(self,z): return abs(complex(z)), self.complex_argument(z)
    def from_polar(self,r,theta):
        if self.settings.angle_unit=="DEG": theta=math.radians(theta)
        elif self.settings.angle_unit=="GRA": theta=theta*math.pi/200
        return cmath.rect(r,theta)

    # Base-N
    def parse_base_token(self,token,base):
        if base not in _SUPPORTED_BASES:
            raise CalculatorError("Argument ERROR: Geçersiz taban")
        token=token.strip().upper()
        try: val=int(token,base)
        except Exception as exc: raise CalculatorError("Syntax ERROR: tabanlı sayı") from exc
        return _signed32(val) if base!=10 else val
    def base_operation(self,a,b=None,op="and"):
        a=_to_32bit(int(a)); b=_to_32bit(int(b or 0))
        if op=="and": r=a&b
        elif op=="or": r=a|b
        elif op=="xor": r=a^b
        elif op=="xnor": r=~(a^b)
        elif op=="Not": r=~a
        elif op=="Neg": r=-_signed32(a)
        else: raise CalculatorError("Argument ERROR")
        return _signed32(r)
    def format_base(self,value,base):
        if base not in _SUPPORTED_BASES:
            raise CalculatorError("Argument ERROR: Geçersiz taban")
        v=_to_32bit(int(value))
        if base==10: return str(_signed32(v))
        if base==16: return f"{v:08X}" if _signed32(v)<0 else f"{v:X}"
        if base==8: return f"{v:011o}" if _signed32(v)<0 else f"{v:o}"
        if base==2: return f"{v:032b}" if _signed32(v)<0 else f"{v:b}"

    def evaluate_base(self, text: str, current_base: int = 10):
        """Evaluate a 32-bit Base-N expression. Supports d/h/b/o prefixes and logical ops."""
        if current_base not in _SUPPORTED_BASES:
            raise CalculatorError("Argument ERROR: Geçersiz taban")
        src=text.strip().replace("×","*").replace("÷","/").replace("−","-")
        if not src: raise CalculatorError("Syntax ERROR")
        if len(src)>2048: raise CalculatorError("Syntax ERROR: Base-N ifadesi çok uzun")
        if "@" in src:
            raise CalculatorError("Syntax ERROR: Base-N ifadesi")
        # Convert whole lexical tokens so generated values never need a
        # user-collidable string marker.  d/h/b/o is an explicit prefix only
        # when its payload is valid in that base; otherwise a valid current-HEX
        # token such as BEEF, DEAD or D00D remains a hexadecimal number.
        prefix_bases={"d":10,"h":16,"b":2,"o":8}
        logical_words={"and","or","xor","xnor","not","neg"}
        base_patterns={
            2: re.compile(r"^[01]+$",re.I),
            8: re.compile(r"^[0-7]+$",re.I),
            10: re.compile(r"^[0-9]+$",re.I),
            16: re.compile(r"^[0-9A-F]+$",re.I),
        }
        def numeric_token(m):
            token=m.group(0)
            lower=token.lower()
            if lower in logical_words:
                return token
            if len(token)>1 and lower[0] in prefix_bases:
                explicit_base=prefix_bases[lower[0]]
                payload=token[1:]
                if base_patterns[explicit_base].fullmatch(payload):
                    return str(self.parse_base_token(payload,explicit_base))
            if base_patterns[current_base].fullmatch(token):
                return str(self.parse_base_token(token,current_base))
            raise CalculatorError("Syntax ERROR: Base-N ifadesi")
        src=re.sub(r"(?<![A-Za-z0-9_])[A-Za-z0-9_]+(?![A-Za-z0-9_])",numeric_token,src)
        # MatMul is an internal sentinel with multiplicative precedence. Raw '@'
        # input is rejected above, so only the xnor keyword can reach this node.
        src=re.sub(r"\bxnor\b","@",src,flags=re.I)
        src=re.sub(r"\bxor\b","^",src,flags=re.I)
        src=re.sub(r"\band\b","&",src,flags=re.I)
        src=re.sub(r"\bor\b","|",src,flags=re.I)
        src=re.sub(r"\bNot\s*\(","~(",src,flags=re.I)
        src=re.sub(r"\bNeg\s*\(","-(",src,flags=re.I)
        import ast
        import operator
        ops={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:_truncating_integer_division,
             ast.BitAnd:operator.and_,ast.BitOr:operator.or_,ast.BitXor:operator.xor,
             ast.MatMult:lambda a,b:~(a^b),ast.Invert:operator.invert,ast.USub:operator.neg}
        def ev(n):
            if isinstance(n,ast.Expression): return ev(n.body)
            if isinstance(n,ast.Constant) and isinstance(n.value,int) and not isinstance(n.value,bool): return n.value
            if isinstance(n,ast.BinOp) and type(n.op) in ops: return ops[type(n.op)](ev(n.left),ev(n.right))
            if isinstance(n,ast.UnaryOp) and type(n.op) in ops: return ops[type(n.op)](ev(n.operand))
            raise CalculatorError("Syntax ERROR: Base-N ifadesi")
        try:r=ev(ast.parse(src,mode="eval"))
        except ZeroDivisionError as exc: raise CalculatorError("Math ERROR: division by zero") from exc
        except CalculatorError: raise
        except Exception as exc: raise CalculatorError("Syntax ERROR: Base-N ifadesi") from exc
        return _signed32(r)

    # Matrix
    def define_matrix(self,name,data):
        if not isinstance(name,str) or name not in self.matrices: raise CalculatorError("Argument ERROR: geçersiz matris adı")
        try: arr=np.array(data,dtype=float)
        except (TypeError,ValueError) as exc: raise CalculatorError("Argument ERROR: geçersiz matris verisi") from exc
        if arr.ndim!=2 or not (1<=arr.shape[0]<=4 and 1<=arr.shape[1]<=4): raise CalculatorError("Dimension ERROR")
        if not np.all(np.isfinite(arr)): raise CalculatorError("Math ERROR: matris verileri sonlu olmalıdır")
        self.matrices[name]=arr; return arr
    def matrix_op(self,op,a,b=None):
        try:
            A=self.matrices.get(a) if isinstance(a,str) else np.array(a,dtype=float)
            B=self.matrices.get(b) if isinstance(b,str) else (np.array(b,dtype=float) if b is not None else None)
        except (TypeError,ValueError) as exc:
            raise CalculatorError("Argument ERROR: geçersiz matris verisi") from exc
        if A is None: raise CalculatorError("Dimension ERROR: matris tanımsız")
        if A.ndim!=2 or not np.all(np.isfinite(A)): raise CalculatorError("Math ERROR: matris verileri geçersiz")
        binary=op in {"+","-","*"}
        if binary and B is None: raise CalculatorError("Dimension ERROR: ikinci matris tanımsız")
        if B is not None and (B.ndim!=2 or not np.all(np.isfinite(B))):
            raise CalculatorError("Math ERROR: matris verileri geçersiz")
        if op in {"+","-"} and A.shape!=B.shape: raise CalculatorError("Dimension ERROR")
        if op=="*" and A.shape[1]!=B.shape[0]: raise CalculatorError("Dimension ERROR")
        if op in {"det","inv"} and A.shape[0]!=A.shape[1]:
            raise CalculatorError("Dimension ERROR: matrix must be square")
        try:
            if op=="+": R=A+B
            elif op=="-": R=A-B
            elif op=="*": R=A@B
            elif op=="det":
                result=float(np.linalg.det(A))
                if not math.isfinite(result): raise CalculatorError("Math ERROR: matris sonucu sonlu değil")
                return result
            elif op=="inv": R=np.linalg.inv(A)
            elif op=="trn": R=A.T
            elif op=="square": R=A@A
            elif op=="cube": R=A@A@A
            elif op=="abs": R=np.abs(A)
            else: raise CalculatorError("Argument ERROR")
        except CalculatorError: raise
        except np.linalg.LinAlgError as exc: raise CalculatorError("Math ERROR: tekil matris") from exc
        except (TypeError,ValueError) as exc: raise CalculatorError("Dimension ERROR") from exc
        if not np.all(np.isfinite(R)): raise CalculatorError("Math ERROR: matris sonucu sonlu değil")
        self.mat_ans=R; return R
    def identity(self,n):
        n=int(n)
        if not 1<=n<=4: raise CalculatorError("Dimension ERROR")
        self.mat_ans=np.eye(n); return self.mat_ans

    # Vector
    def define_vector(self,name,data):
        if not isinstance(name,str) or name not in self.vectors: raise CalculatorError("Argument ERROR: geçersiz vektör adı")
        try: arr=np.array(data,dtype=float)
        except (TypeError,ValueError) as exc: raise CalculatorError("Argument ERROR: geçersiz vektör verisi") from exc
        if arr.ndim!=1 or len(arr) not in (2,3): raise CalculatorError("Dimension ERROR")
        if not np.all(np.isfinite(arr)): raise CalculatorError("Math ERROR: vektör verileri sonlu olmalıdır")
        self.vectors[name]=arr; return arr
    def vector_op(self,op,a,b=None,scalar=None):
        try:
            A=self.vectors.get(a) if isinstance(a,str) else np.array(a,dtype=float)
            B=self.vectors.get(b) if isinstance(b,str) else (np.array(b,dtype=float) if b is not None else None)
        except (TypeError,ValueError) as exc:
            raise CalculatorError("Argument ERROR: geçersiz vektör verisi") from exc
        if A is None: raise CalculatorError("Dimension ERROR")
        if A.ndim!=1 or len(A) not in (2,3):
            raise CalculatorError("Math ERROR: vektör verileri geçersiz")
        if not np.all(np.isfinite(A)):
            if op=="angle": raise CalculatorError("Math ERROR: sıfır vektörün açısı tanımsızdır")
            raise CalculatorError("Math ERROR: vektör verileri geçersiz")
        binary=op in {"+","-","dot","cross","angle"}
        if binary and B is None: raise CalculatorError("Dimension ERROR: ikinci vektör tanımsız")
        if B is not None:
            if B.ndim!=1 or len(B) not in (2,3):
                raise CalculatorError("Math ERROR: vektör verileri geçersiz")
            if not np.all(np.isfinite(B)):
                if op=="angle": raise CalculatorError("Math ERROR: sıfır vektörün açısı tanımsızdır")
                raise CalculatorError("Math ERROR: vektör verileri geçersiz")
            if binary and A.shape!=B.shape: raise CalculatorError("Dimension ERROR")
        try:
            if op=="+": R=A+B
            elif op=="-": R=A-B
            elif op=="scale":
                scale=_finite_real_float(scalar,"Math ERROR: skaler sonlu reel olmalıdır")
                R=scale*A
            elif op=="dot":
                result=float(np.dot(A,B))
                if not math.isfinite(result): raise CalculatorError("Math ERROR: vektör sonucu sonlu değil")
                return result
            elif op=="cross": R=np.cross(A,B)
            elif op=="abs":
                result=float(np.linalg.norm(A))
                if not math.isfinite(result): raise CalculatorError("Math ERROR: vektör sonucu sonlu değil")
                return result
            elif op=="unit":
                n=np.linalg.norm(A)
                if not math.isfinite(float(n)) or n==0: raise CalculatorError("Math ERROR")
                R=A/n
            elif op=="angle":
                norm_a=float(np.linalg.norm(A)); norm_b=float(np.linalg.norm(B))
                if not math.isfinite(norm_a) or not math.isfinite(norm_b) or norm_a==0 or norm_b==0:
                    raise CalculatorError("Math ERROR: sıfır vektörün açısı tanımsızdır")
                c=float(np.dot(A,B)/(norm_a*norm_b)); c=max(-1,min(1,c)); ang=math.acos(c)
                if self.settings.angle_unit=="DEG": ang=math.degrees(ang)
                elif self.settings.angle_unit=="GRA": ang=ang*200/math.pi
                return ang
            else: raise CalculatorError("Argument ERROR")
        except CalculatorError: raise
        except (TypeError,ValueError) as exc: raise CalculatorError("Dimension ERROR") from exc
        if not np.all(np.isfinite(R)): raise CalculatorError("Math ERROR: vektör sonucu sonlu değil")
        self.vct_ans=np.atleast_1d(R); return R

    # Statistics & regression
    def one_var_stats(self,x:Iterable[float],freq:Iterable[float] | None=None):
        try:
            x=np.asarray(list(x),dtype=float)
        except (TypeError, ValueError) as exc:
            raise CalculatorError("Argument ERROR: geçersiz veri") from exc
        if x.ndim != 1: raise CalculatorError("Dimension ERROR")
        if x.size==0: raise CalculatorError("Argument ERROR: veri yok")
        if not np.all(np.isfinite(x)): raise CalculatorError("Math ERROR: veriler sonlu olmalıdır")
        if freq is not None:
            try:
                f=np.asarray(list(freq),dtype=float)
            except (TypeError, ValueError) as exc:
                raise CalculatorError("Argument ERROR: geçersiz frekans") from exc
            if f.ndim != 1 or len(f)!=len(x): raise CalculatorError("Dimension ERROR")
            if not np.all(np.isfinite(f)): raise CalculatorError("Math ERROR: frekanslar sonlu olmalıdır")
            if np.any(f < 0) or np.any(f != np.floor(f)):
                raise CalculatorError("Argument ERROR: frekanslar negatif olmayan tam sayı olmalıdır")
            total=sum(int(value) for value in f)
            if total <= 0: raise CalculatorError("Argument ERROR: toplam frekans pozitif olmalıdır")
            weights=f.astype(np.int64)
            mean=float(np.sum(x*weights)/total)
            variance=float(np.sum(weights*(x-mean)**2)/total)
            sample_variance=float(np.sum(weights*(x-mean)**2)/(total-1)) if total>1 else float('nan')
            # Quantiles retain NumPy's existing midpoint semantics without an
            # expanded sample.  Sorting weighted observations is O(unique n).
            order=np.argsort(x); values=x[order]; cumulative=np.cumsum(weights[order])
            def weighted_value(position):
                return float(values[np.searchsorted(cumulative, position, side="left")])
            def midpoint_percentile(percent):
                position=(total-1)*percent/100
                return (weighted_value(math.floor(position)+1)+weighted_value(math.ceil(position)+1))/2
            q1,med,q3=(midpoint_percentile(p) for p in (25,50,75))
            result={"n":total,"Σx":float(np.sum(x*weights)),"Σx²":float(np.sum(x*x*weights)),"x̄":mean,"σx²":variance,"σx":math.sqrt(variance),
                    "sx²":sample_variance,"sx":math.sqrt(sample_variance) if total>1 else float('nan'),
                    "min(x)":float(x.min()),"Q1":q1,"Med":med,"Q3":q3,"max(x)":float(x.max())}
        else:
            with np.errstate(over="ignore",invalid="ignore",divide="ignore"):
                q1,med,q3=np.percentile(x,[25,50,75],method="midpoint")
                result={"n":len(x),"Σx":x.sum(),"Σx²":np.sum(x*x),"x̄":x.mean(),"σx²":x.var(ddof=0),"σx":x.std(ddof=0),
                        "sx²":x.var(ddof=1) if len(x)>1 else float('nan'),"sx":x.std(ddof=1) if len(x)>1 else float('nan'),
                        "min(x)":x.min(),"Q1":q1,"Med":med,"Q3":q3,"max(x)":x.max()}
        for name,value in result.items():
            if name in {"sx²","sx"} and result["n"]==1 and math.isnan(float(value)):
                continue
            if not math.isfinite(float(value)):
                raise CalculatorError("Math ERROR: istatistik sonucu sonlu değil")
        return result
    def regression(self,x,y,kind="linear"):
        try:
            x=np.asarray(x,dtype=float); y=np.asarray(y,dtype=float)
        except (TypeError, ValueError) as exc:
            raise CalculatorError("Argument ERROR: geçersiz regresyon verisi") from exc
        if x.ndim != 1 or y.ndim != 1 or len(x)!=len(y): raise CalculatorError("Dimension ERROR")
        if len(x)<2: raise CalculatorError("Dimension ERROR")
        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            raise CalculatorError("Math ERROR: regresyon verileri sonlu olmalıdır")
        if kind not in {"linear", "quadratic", "log", "exp_e", "exp_b", "power", "inverse"}:
            raise CalculatorError("Argument ERROR")

        tx=x; ty=y
        if kind in {"log", "power"}:
            if np.any(x<=0): raise CalculatorError("Math ERROR")
            tx=np.log(x)
        elif kind=="inverse":
            if np.any(x==0): raise CalculatorError("Math ERROR")
            with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
                tx=1/x
        if kind in {"exp_e", "exp_b", "power"}:
            if np.any(y<=0): raise CalculatorError("Math ERROR")
            ty=np.log(y)
        if not np.all(np.isfinite(tx)) or not np.all(np.isfinite(ty)):
            raise CalculatorError("Math ERROR: dönüştürülmüş regresyon verileri sonlu olmalıdır")

        degree=2 if kind=="quadratic" else 1
        if np.unique(tx).size < degree + 1:
            raise CalculatorError("Math ERROR: bağımsız veri çeşitliliği yetersiz")
        rank_warning=getattr(getattr(np,"exceptions",np),"RankWarning",Warning)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error",rank_warning)
                coeffs=np.polyfit(tx,ty,degree)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError, rank_warning) as exc:
            raise CalculatorError("Math ERROR: regresyon hesaplanamadı") from exc
        if not np.all(np.isfinite(coeffs)):
            raise CalculatorError("Math ERROR: regresyon katsayıları sonlu değil")

        if kind=="quadratic":
            c,b,a=coeffs
            return {"a":a,"b":b,"c":c,"predict":lambda X:a+b*X+c*X*X}
        b,a=coeffs
        if kind=="linear":
            with np.errstate(divide="ignore",invalid="ignore"):
                r=np.corrcoef(x,y)[0,1]
            if not np.isfinite(r):
                r=None
            return {"a":a,"b":b,"r":r,"predict":lambda X:a+b*X}
        if kind=="log":
            return {"a":a,"b":b,"predict":lambda X:a+b*np.log(X)}
        if kind=="inverse":
            return {"a":a,"b":b,"predict":lambda X:a+b/X}
        with np.errstate(over="ignore",invalid="ignore"):
            scale=np.exp(a)
            base=np.exp(b) if kind=="exp_b" else None
        if not math.isfinite(float(scale)) or (base is not None and not math.isfinite(float(base))):
            raise CalculatorError("Math ERROR: regresyon katsayıları sonlu değil")
        if kind=="exp_e":
            return {"a":scale,"b":b,"predict":lambda X:scale*np.exp(b*X)}
        if kind=="exp_b":
            return {"a":scale,"b":base,"predict":lambda X:scale*(base**X)}
        return {"a":scale,"b":b,"predict":lambda X:scale*(X**b)}
    @staticmethod
    def normal_P(t): return stats.norm.cdf(t)
    @staticmethod
    def normal_Q(t): return abs(stats.norm.cdf(t)-0.5)
    @staticmethod
    def normal_R(t): return stats.norm.sf(t)

    # Distributions
    def distribution(self,kind,**kw):
        def finite(name):
            try:
                value = float(kw[name])
            except (KeyError, TypeError, ValueError) as exc:
                raise CalculatorError(f"Argument ERROR: {name}") from exc
            if not math.isfinite(value):
                raise CalculatorError(f"Math ERROR: {name} sonlu olmalıdır")
            return value

        def nonnegative_integer(name):
            value = finite(name)
            if value < 0 or not value.is_integer():
                raise CalculatorError(f"Argument ERROR: {name} negatif olmayan tam sayı olmalıdır")
            return int(value)

        try:
            if kind in {"Normal PD", "Normal CD", "Inverse Normal"}:
                mu = finite("mu")
                sigma = finite("sigma")
                if sigma <= 0:
                    raise CalculatorError("Math ERROR: sigma pozitif olmalıdır")
                if kind == "Normal PD":
                    result = stats.norm.pdf(finite("x"), loc=mu, scale=sigma)
                elif kind == "Normal CD":
                    lower = finite("lower")
                    upper = finite("upper")
                    if lower > upper:
                        raise CalculatorError("Argument ERROR: alt sınır üst sınırı aşamaz")
                    result = stats.norm.cdf(upper,loc=mu,scale=sigma)-stats.norm.cdf(lower,loc=mu,scale=sigma)
                else:
                    area = finite("area")
                    if not 0 < area < 1:
                        raise CalculatorError("Argument ERROR: area 0 ile 1 arasında olmalıdır")
                    result = stats.norm.ppf(area,loc=mu,scale=sigma)
            elif kind in {"Binomial PD", "Binomial CD"}:
                x = nonnegative_integer("x")
                n = nonnegative_integer("N")
                p = finite("p")
                if not 0 <= p <= 1:
                    raise CalculatorError("Argument ERROR: p 0 ile 1 arasında olmalıdır")
                result = stats.binom.pmf(x,n,p) if kind == "Binomial PD" else stats.binom.cdf(x,n,p)
            elif kind in {"Poisson PD", "Poisson CD"}:
                x = nonnegative_integer("x")
                lam = finite("lam")
                if lam < 0:
                    raise CalculatorError("Argument ERROR: lambda negatif olamaz")
                result = stats.poisson.pmf(x,lam) if kind == "Poisson PD" else stats.poisson.cdf(x,lam)
            else:
                raise CalculatorError("Argument ERROR")
        except CalculatorError:
            raise
        except Exception as exc:
            raise CalculatorError("Math ERROR") from exc
        if not math.isfinite(float(result)):
            raise CalculatorError("Math ERROR: dağılım sonucu sonlu değil")
        return result

    # Equation / inequality / ratio
    def simultaneous(self,A,b):
        try:
            A=np.asarray(A,dtype=float); b=np.asarray(b,dtype=float)
        except (TypeError,ValueError,OverflowError) as exc:
            raise CalculatorError("Argument ERROR: geçersiz denklem verisi") from exc
        if A.ndim!=2 or A.shape[0]!=A.shape[1] or A.shape[0] not in (2,3,4) or b.shape!=(A.shape[0],):
            raise CalculatorError("Dimension ERROR")
        if not np.all(np.isfinite(A)) or not np.all(np.isfinite(b)):
            raise CalculatorError("Math ERROR: denklem verileri sonlu olmalıdır")
        try:
            result=np.linalg.solve(A,b)
        except np.linalg.LinAlgError as exc:
            raise CalculatorError("Math ERROR") from exc
        if not np.all(np.isfinite(result)):
            raise CalculatorError("Math ERROR: denklem sonucu sonlu değil")
        return result
    def polynomial_roots(self,coeffs):
        coeffs=[complex(c) for c in coeffs]
        if len(coeffs)-1 not in (2,3,4): raise CalculatorError("Argument ERROR")
        if any(not (math.isfinite(value.real) and math.isfinite(value.imag)) for value in coeffs):
            raise CalculatorError("Math ERROR: polynomial coefficients must be finite")
        if coeffs[0] == 0:
            raise CalculatorError("Argument ERROR: polynomial leading coefficient must not be zero")
        roots=np.roots(coeffs)
        if not self.settings.equation_complex: roots=np.array([r.real for r in roots if abs(r.imag)<1e-10])
        return roots
    def inequality(self,coeffs,relation):
        try: coeffs=[float(c) for c in coeffs]
        except (TypeError,ValueError) as exc: raise CalculatorError("Argument ERROR") from exc
        if len(coeffs)-1 not in (1,2,3,4): raise CalculatorError("Argument ERROR")
        if not all(math.isfinite(value) for value in coeffs): raise CalculatorError("Math ERROR: inequality coefficients must be finite")
        if coeffs[0] == 0: raise CalculatorError("Argument ERROR: inequality leading coefficient must not be zero")
        if relation not in {">","<","≥","<=","≤",">="}: raise CalculatorError("Argument ERROR")
        x=sp.Symbol('x', real=True); poly=sum(sp.Float(c)*x**(len(coeffs)-1-i) for i,c in enumerate(coeffs))
        rel={">":poly>0,"<":poly<0,"≥":poly>=0,"<=":poly<=0,"≤":poly<=0,">=":poly>=0}[relation]
        return sp.reduce_inequalities(rel,x)
    def ratio(self,kind,**kw):
        def finite(name):
            try:
                return _finite_real_float(kw[name],"Math ERROR: oran değerleri sonlu reel olmalıdır")
            except KeyError as exc:
                raise CalculatorError("Argument ERROR: oran değeri eksik") from exc
        if kind=="A:B=X:D":
            A,B,D=finite("A"),finite("B"),finite("D")
            if B==0: raise CalculatorError("Math ERROR")
            result=A*D/B
        elif kind=="A:B=C:X":
            A,B,C=finite("A"),finite("B"),finite("C")
            if A==0: raise CalculatorError("Math ERROR")
            result=B*C/A
        else:
            raise CalculatorError("Argument ERROR: unsupported ratio form")
        if not math.isfinite(result):
            raise CalculatorError("Math ERROR: oran sonucu sonlu değil")
        return result

    def convert(self,name,value):
        if name not in CONVERSIONS: raise CalculatorError("Argument ERROR")
        return CONVERSIONS[name](float(value))

    def format_result(self,value,approximate=False):
        def _exact_scalar(v):
            _require_exact_display_budget(v)
            if isinstance(v, sp.Rational) and v.q != 1 and self.settings.fraction_result=="a b/c" and abs(v.p) > v.q:
                sign='-' if v < 0 else ''
                p=abs(int(v.p)); q=int(v.q); whole,rem=divmod(p,q)
                return f"{sign}{whole} {rem}/{q}" if rem else f"{sign}{whole}"
            return str(v).replace("sqrt","√").replace("**","^")

        def _numeric_part(v, signed=False):
            v=float(v)
            if not math.isfinite(v):
                raise CalculatorError("Math ERROR: sayısal sonuç görüntüleme aralığını aşıyor")
            mode=self.settings.number_format; n=self.settings.number_digits
            if v == 0:
                s="0"
            elif mode != "Sci" and abs(v) < 1e-6:
                # Keep a real, non-zero result visible.  Decimal's fixed-point
                # rendering avoids both a display-only zero threshold and e
                # notation for the small values users commonly encounter.
                s=format(Decimal(str(v)), "f")
                if signed and v > 0:
                    s="+"+s
            elif mode=="Fix": s=f"{v:+.{n}f}" if signed else f"{v:.{n}f}"
            elif mode=="Sci": s=f"{v:+.{max(0,n-1)}e}" if signed else f"{v:.{max(0,n-1)}e}"
            else: s=f"{v:+.12g}" if signed else f"{v:.12g}"
            if self.settings.digit_separator and 'e' not in s.lower():
                sign=''
                core=s
                if core[:1] in '+-': sign,core=core[0],core[1:]
                try:
                    a,b=(core.split('.')+[None])[:2]
                    a=f"{int(a):,}"
                    core=a+(('.'+b) if b is not None else '')
                except Exception:
                    pass
                s=sign+core
            if self.settings.decimal_mark=="Comma": s=s.replace('.',',')
            return s

        if isinstance(value,np.ndarray):
            return np.array2string(value,precision=self.settings.number_digits,suppress_small=False)

        if isinstance(value,complex):
            if abs(value.imag)<1e-12:
                value=value.real
            else:
                if self.settings.complex_format=="r∠θ":
                    r,a=self.to_polar(value); return f"{_numeric_part(r)}∠{_numeric_part(a)}"
                real=_numeric_part(value.real)
                imag=_numeric_part(abs(value.imag))
                sign='+' if value.imag>=0 else '-'
                return f"{real}{sign}{imag}i"

        if isinstance(value,sp.Basic):
            if value.has(sp.I):
                if not approximate and self.settings.input_output in ("MathI/MathO","LineI/LineO"):
                    real=sp.simplify(sp.re(value)); imag=sp.simplify(sp.im(value))
                    if imag.is_zero is True:
                        return _exact_scalar(real)
                    real_is_zero=real.is_zero is True
                    if imag.is_nonnegative is True:
                        sign='' if real_is_zero else '+'
                        imag_abs=imag
                    elif imag.is_negative is True:
                        sign='-'
                        imag_abs=-imag
                    else:
                        # A symbolic imaginary coefficient has no truth value for
                        # Python comparisons.  Keep the original expression in a
                        # stable, unambiguous exact form instead.
                        return re.sub(r"\bI\b", "i", _exact_scalar(value))
                    real_s='' if real_is_zero else _exact_scalar(real)
                    imag_abs=sp.simplify(imag_abs)
                    imag_s='i' if imag_abs == 1 else _exact_scalar(imag_abs)+'i'
                    return f"{real_s}{sign}{imag_s}"
                return self.format_result(complex(sp.N(value,15)))
            if approximate or self.settings.input_output in ("MathI/DecimalO","LineI/DecimalO"):
                value=float(sp.N(value,15))
            else:
                return _exact_scalar(value)

        try:
            v=float(value)
            if not math.isfinite(v):
                raise CalculatorError("Math ERROR: sayısal sonuç görüntüleme aralığını aşıyor")
            return _numeric_part(v)
        except CalculatorError:
            raise
        except Exception:
            return str(value)
