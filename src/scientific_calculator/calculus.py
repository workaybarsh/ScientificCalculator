"""Bounded real and complex calculus operations for the calculator engine.

The mixin deliberately depends on the engine's safe parser, CAS boundary,
history formatter, and state.  Keeping those stateful concerns in the engine
while isolating calculus policy makes the numerical/symbolic behavior easier
to review and test without changing its public API.
"""
from __future__ import annotations

import math
import re
import string
import warnings
from collections.abc import Mapping

import numpy as np
import sympy as sp
from scipy.integrate import IntegrationWarning, dblquad, quad, tplquad

from .errors import CalculatorError
from .numeric_validation import finite_complex as _finite_complex
from .numeric_validation import finite_real_float as _finite_real_float


class CalculusMixin:
    """Calculus behavior mixed into :class:`ScientificCalculatorEngine`."""

    @staticmethod
    def _validate_calculus_variable(variable: str, *, label: str = "Değişken") -> None:
        if not isinstance(variable, str) or len(variable) != 1 or not variable.isascii() or not variable.isalpha():
            raise CalculatorError(f"Syntax ERROR: {label} tek harf olmalıdır")

    @staticmethod
    def _calculus_symbol_locals(allowed: dict[str, sp.Symbol]) -> dict[str, sp.Symbol]:
        """Keep calculus variables symbolic instead of reading calculator memory.

        A path such as ``x(t)`` must not silently substitute a saved calculator
        memory value called ``x``.  All ordinary one-letter names therefore
        remain symbols until the operation explicitly validates its variables.
        Euler's ``e`` and the imaginary unit ``i`` retain their normal parser
        meanings.
        """
        locals_ = {
            letter: sp.Symbol(letter)
            for letter in string.ascii_letters
            if letter not in {"e", "i", "I"}
        }
        locals_.update(allowed)
        return locals_

    def _parse_integral_bound(self, bound: str) -> sp.Expr:
        if not isinstance(bound, str):
            raise CalculatorError("Math ERROR: integral sınırı metin olmalıdır")
        aliases = {
            "inf": sp.oo, "+inf": sp.oo, "infinity": sp.oo, "+infinity": sp.oo,
            "∞": sp.oo, "+∞": sp.oo, "oo": sp.oo, "+oo": sp.oo,
            "-inf": -sp.oo, "-infinity": -sp.oo, "-∞": -sp.oo, "-oo": -sp.oo,
        }
        normalized = bound.strip().lower().replace(" ", "")
        if normalized in aliases:
            return aliases[normalized]
        result = self.parse(bound)
        if result.free_symbols:
            raise CalculatorError("Math ERROR: integral sınırı sayısal olmalıdır")
        return result

    @staticmethod
    def _integral_bound_float(bound: sp.Expr) -> float:
        if bound == sp.oo:
            return math.inf
        if bound == -sp.oo:
            return -math.inf
        return _finite_real_float(bound, "Math ERROR: integral sınırları sonlu reel olmalıdır")

    def _integral_segments(self, expr: sp.Expr, symbol: sp.Symbol, lower: sp.Expr, upper: sp.Expr):
        """Split known interior singularities so a Cauchy principal value is never accepted."""
        lo, hi = self._integral_bound_float(lower), self._integral_bound_float(upper)
        try:
            singular_set = self._run_cas("singularities", {"expression": expr, "symbol": symbol})
        except Exception:
            singular_set = sp.S.EmptySet
        points: list[tuple[float, sp.Expr]] = []
        if isinstance(singular_set, sp.FiniteSet):
            low, high = sorted((lo, hi))
            for point in singular_set:
                try:
                    point_value = _finite_real_float(point, "Math ERROR")
                except CalculatorError:
                    continue
                if low < point_value < high:
                    points.append((point_value, point))
        points.sort(key=lambda item: item[0], reverse=lo > hi)
        boundaries = [lower, *(point for _, point in points), upper]
        return list(zip(boundaries, boundaries[1:], strict=False)), bool(points)

    @staticmethod
    def _exact_integral_value(value: object, *, allow_complex: bool):
        if isinstance(value, sp.Integral):
            return None
        if isinstance(value, sp.Basic) and value.free_symbols:
            raise CalculatorError("Math ERROR: integral sayısal sonuç vermedi")
        if allow_complex:
            _finite_complex(value, "Math ERROR: integral sonlu karmaşık değil")
            return value if isinstance(value, sp.Basic) else sp.sympify(value)
        return _finite_real_float(value, "Math ERROR: integral sonlu reel değil")

    def _numeric_integral(self, expr: sp.Expr, symbol: sp.Symbol, segments, *, tol: float, allow_complex: bool):
        if expr.free_symbols - {symbol}:
            raise CalculatorError("Math ERROR: integralde bilinmeyen değişken var")
        try:
            tolerance = float(tol)
        except (TypeError, ValueError) as exc:
            raise CalculatorError("Argument ERROR: integral toleransı pozitif sonlu sayı olmalıdır") from exc
        if not math.isfinite(tolerance) or not 0 < tolerance <= 1e-2:
            raise CalculatorError("Argument ERROR: integral toleransı pozitif sonlu sayı olmalıdır")
        modules = ["numpy", "cmath", "math"] if allow_complex else ["numpy", "math"]
        try:
            fn = sp.lambdify(symbol, expr, modules=modules)
            total = 0j if allow_complex else 0.0
            with warnings.catch_warnings():
                warnings.simplefilter("error", IntegrationWarning)
                warnings.simplefilter("error", RuntimeWarning)
                for lower, upper in segments:
                    lo, hi = self._integral_bound_float(lower), self._integral_bound_float(upper)
                    if allow_complex:
                        real, real_error = quad(
                            lambda value: float(np.real(fn(value))), lo, hi,
                            epsabs=tolerance, epsrel=tolerance, limit=300,
                        )
                        imag, imag_error = quad(
                            lambda value: float(np.imag(fn(value))), lo, hi,
                            epsabs=tolerance, epsrel=tolerance, limit=300,
                        )
                        if not (math.isfinite(real_error) and math.isfinite(imag_error)):
                            raise CalculatorError("Math ERROR: integral hata tahmini sonlu değil")
                        total += complex(real, imag)
                    else:
                        value, error = quad(fn, lo, hi, epsabs=tolerance, epsrel=tolerance, limit=300)
                        if not math.isfinite(float(error)):
                            raise CalculatorError("Math ERROR: integral hata tahmini sonlu değil")
                        total += value
        except CalculatorError:
            raise
        except Exception as exc:
            raise CalculatorError("Math ERROR: integral could not be evaluated") from exc
        if allow_complex:
            return _finite_complex(total, "Math ERROR: integral sonucu sonlu karmaşık değil")
        return _finite_real_float(total, "Math ERROR: integral sonucu sonlu reel değil")

    def _definite_integral_expression(
        self, expr: sp.Expr, lower: sp.Expr, upper: sp.Expr, symbol: sp.Symbol, *, tol: float, allow_complex: bool,
    ):
        if expr.free_symbols - {symbol}:
            raise CalculatorError("Math ERROR: integralde bilinmeyen değişken var")
        segments, has_interior_singularity = self._integral_segments(expr, symbol, lower, upper)
        exact_values = []
        try:
            for segment_lower, segment_upper in segments:
                exact = self._run_cas("definite_integral", {
                    "expression": expr, "symbol": symbol, "lower": segment_lower, "upper": segment_upper,
                })
                value = self._exact_integral_value(exact, allow_complex=allow_complex)
                if value is None:
                    exact_values = []
                    break
                exact_values.append(value)
            if exact_values:
                exact_result = sum(exact_values, sp.Integer(0))
                if allow_complex:
                    _finite_complex(exact_result, "Math ERROR: integral sonlu karmaşık değil")
                    return exact_result, False
                return _finite_real_float(exact_result, "Math ERROR: integral sonlu reel değil"), True
        except CalculatorError:
            if has_interior_singularity:
                raise CalculatorError("Math ERROR: integral iç tekilliği yakınsak değil") from None
            raise
        except Exception:
            pass
        try:
            numeric = self._numeric_integral(
                expr, symbol, segments, tol=tol, allow_complex=allow_complex,
            )
        except CalculatorError:
            if has_interior_singularity:
                raise CalculatorError("Math ERROR: integral iç tekilliği yakınsak değil") from None
            raise
        return numeric, True

    def _commit_definite_integral(self, expression: str, result, *, approximate: bool) -> None:
        self.ans = result if isinstance(result, sp.Basic) else sp.sympify(result)
        self._remember_history(expression, self.format_result(result, approximate=approximate))

    def definite_integral(self, integrand, lower, upper, variable="x", tol=1e-10):
        """Real definite integral, including convergent improper integrals."""
        self._validate_calculus_variable(variable)
        x = sp.Symbol(variable)
        expr = self.parse(integrand, {variable: x})
        lo_expr, hi_expr = self._parse_integral_bound(lower), self._parse_integral_bound(upper)
        result, approximate = self._definite_integral_expression(
            expr, lo_expr, hi_expr, x, tol=tol, allow_complex=False,
        )
        self._commit_definite_integral(
            f"∫{lower}→{upper} {integrand} d{variable}", result, approximate=approximate,
        )
        return result

    def complex_definite_integral(self, integrand, lower, upper, variable="z", tol=1e-10):
        """Complex-valued definite integral over a real parameter interval."""
        self._validate_calculus_variable(variable)
        z = sp.Symbol(variable)
        expr = self.parse_symbolic(integrand, {variable: z})
        lo_expr, hi_expr = self._parse_integral_bound(lower), self._parse_integral_bound(upper)
        result, approximate = self._definite_integral_expression(
            expr, lo_expr, hi_expr, z, tol=tol, allow_complex=True,
        )
        self._commit_definite_integral(
            f"∫{lower}→{upper} {integrand} d{variable}", result, approximate=approximate,
        )
        return result

    def contour_integral(
        self, integrand, path, lower, upper, complex_variable="z", parameter="t", tol=1e-10,
    ):
        """Integrate f(z) dz along z=path(parameter) on a finite real interval."""
        self._validate_calculus_variable(complex_variable, label="Karmaşık değişken")
        self._validate_calculus_variable(parameter, label="Yol parametresi")
        if complex_variable == parameter:
            raise CalculatorError("Syntax ERROR: Karmaşık değişken ve yol parametresi farklı olmalıdır")
        z, t = sp.Symbol(complex_variable), sp.Symbol(parameter, real=True)
        expr = self.parse_symbolic(integrand, self._calculus_symbol_locals({complex_variable: z}))
        gamma = self.parse_symbolic(path, self._calculus_symbol_locals({parameter: t}))
        if expr.free_symbols - {z} or gamma.free_symbols - {t}:
            raise CalculatorError("Math ERROR: kontur yalnız belirtilen değişkenleri içermelidir")
        lo_expr, hi_expr = self._parse_integral_bound(lower), self._parse_integral_bound(upper)
        if lo_expr in (sp.oo, -sp.oo) or hi_expr in (sp.oo, -sp.oo):
            raise CalculatorError("Math ERROR: kontur sınırları sonlu reel olmalıdır")
        try:
            derivative = self._run_cas("differentiate", {"expression": gamma, "symbol": t})
            transformed = self._run_cas("simplify", {"expression": expr.subs(z, gamma) * derivative})
        except Exception as exc:
            raise CalculatorError("Math ERROR: kontur integrali hazırlanamadı") from exc
        result, approximate = self._definite_integral_expression(
            transformed, lo_expr, hi_expr, t, tol=tol, allow_complex=True,
        )
        self._commit_definite_integral(
            f"∫[{path}; {lower}→{upper}] {integrand} d{complex_variable}", result, approximate=approximate,
        )
        return result

    @classmethod
    def _validate_distinct_calculus_variables(cls, *variables: str) -> None:
        for variable in variables:
            cls._validate_calculus_variable(variable)
        if len(set(variables)) != len(variables):
            raise CalculatorError("Syntax ERROR: integral değişkenleri farklı olmalıdır")

    def _parse_finite_multivariate_bound(
        self, bound: str, allowed_symbols: tuple[sp.Symbol, ...] = (), *, label: str = "integral sınırı",
    ) -> sp.Expr:
        """Parse a real finite bound which may depend only on outer variables."""
        if not isinstance(bound, str):
            raise CalculatorError(f"Math ERROR: {label} metin olmalıdır")
        aliases = {"inf", "+inf", "infinity", "+infinity", "∞", "+∞", "oo", "+oo", "-inf", "-infinity", "-∞", "-oo"}
        if bound.strip().lower().replace(" ", "") in aliases:
            raise CalculatorError("Math ERROR: çoklu integral sınırları sonlu reel olmalıdır")
        locals_ = self._calculus_symbol_locals({str(symbol): symbol for symbol in allowed_symbols})
        result = self.parse_symbolic(bound, locals_)
        if result.free_symbols - set(allowed_symbols):
            raise CalculatorError(f"Math ERROR: {label} yalnız dış integral değişkenlerini içerebilir")
        if result.has(sp.oo, -sp.oo, sp.zoo, sp.nan):
            raise CalculatorError("Math ERROR: çoklu integral sınırları sonlu reel olmalıdır")
        return result

    @staticmethod
    def _numeric_real_callable(expression: sp.Expr, symbols: tuple[sp.Symbol, ...], *, label: str):
        try:
            raw = sp.lambdify(symbols, expression, modules=["numpy", "math"])
        except Exception as exc:
            raise CalculatorError(f"Math ERROR: {label} sayısal hesaplamaya hazırlanamadı") from exc

        def evaluate(*values: float) -> float:
            try:
                return _finite_real_float(raw(*values), f"Math ERROR: {label} sonlu reel olmalıdır")
            except CalculatorError:
                raise
            except Exception as exc:
                raise CalculatorError(f"Math ERROR: {label} hesaplanamadı") from exc

        return evaluate

    def _try_exact_nested_integral(
        self, expression: sp.Expr, specifications: tuple[tuple[sp.Symbol, sp.Expr, sp.Expr], ...], *,
        allow_complex: bool = False,
    ) -> object | None:
        """Return a closed nested integral, preserving an exact complex result."""
        result = expression
        try:
            for symbol, lower, upper in reversed(specifications):
                result = self._run_cas("definite_integral", {
                    "expression": result, "symbol": symbol, "lower": lower, "upper": upper,
                })
                if isinstance(result, sp.Integral):
                    return None
            if allow_complex:
                _finite_complex(result, "Math ERROR: integral sonlu karmaşık değil")
                return result
            return _finite_real_float(result, "Math ERROR: integral sonlu reel değil")
        except Exception:
            return None

    @staticmethod
    def _finish_numeric_multivariate(value: object, error: object) -> float:
        result = _finite_real_float(value, "Math ERROR: çoklu integral sonucu sonlu reel değil")
        estimated_error = _finite_real_float(error, "Math ERROR: çoklu integral hata tahmini sonlu değil")
        if estimated_error < 0:
            raise CalculatorError("Math ERROR: çoklu integral hata tahmini geçersiz")
        return result

    def _numeric_double_integral(
        self, expression: sp.Expr, outer: sp.Symbol, inner: sp.Symbol,
        outer_lower: sp.Expr, outer_upper: sp.Expr, inner_lower: sp.Expr, inner_upper: sp.Expr, *, tol: float,
    ) -> float:
        try:
            tolerance = float(tol)
        except (TypeError, ValueError) as exc:
            raise CalculatorError("Argument ERROR: integral toleransı pozitif sonlu sayı olmalıdır") from exc
        if not math.isfinite(tolerance) or not 0 < tolerance <= 1e-2:
            raise CalculatorError("Argument ERROR: integral toleransı pozitif sonlu sayı olmalıdır")
        outer_lo = _finite_real_float(outer_lower, "Math ERROR: integral sınırları sonlu reel olmalıdır")
        outer_hi = _finite_real_float(outer_upper, "Math ERROR: integral sınırları sonlu reel olmalıdır")
        integrand = self._numeric_real_callable(expression, (outer, inner), label="integrand")
        lower = self._numeric_real_callable(inner_lower, (outer,), label="iç integral sınırı")
        upper = self._numeric_real_callable(inner_upper, (outer,), label="iç integral sınırı")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", IntegrationWarning)
                warnings.simplefilter("error", RuntimeWarning)
                value, error = dblquad(
                    lambda inner_value, outer_value: integrand(outer_value, inner_value),
                    outer_lo, outer_hi, lower, upper, epsabs=tolerance, epsrel=tolerance,
                )
        except CalculatorError:
            raise
        except Exception as exc:
            raise CalculatorError("Math ERROR: çift katlı integral hesaplanamadı") from exc
        return self._finish_numeric_multivariate(value, error)

    @staticmethod
    def _numeric_complex_callable(expression: sp.Expr, symbols: tuple[sp.Symbol, ...], *, label: str):
        try:
            raw = sp.lambdify(symbols, expression, modules=["numpy", "cmath", "math"])
        except Exception as exc:
            raise CalculatorError(f"Math ERROR: {label} sayısal hesaplamaya hazırlanamadı") from exc

        def evaluate(*values: float) -> complex:
            try:
                return _finite_complex(raw(*values), f"Math ERROR: {label} sonlu karmaşık olmalıdır")
            except CalculatorError:
                raise
            except Exception as exc:
                raise CalculatorError(f"Math ERROR: {label} hesaplanamadı") from exc

        return evaluate

    def _numeric_complex_double_integral(
        self, expression: sp.Expr, outer: sp.Symbol, inner: sp.Symbol,
        outer_lower: sp.Expr, outer_upper: sp.Expr, inner_lower: sp.Expr, inner_upper: sp.Expr, *, tol: float,
    ) -> complex:
        try:
            tolerance = float(tol)
        except (TypeError, ValueError) as exc:
            raise CalculatorError("Argument ERROR: integral toleransı pozitif sonlu sayı olmalıdır") from exc
        if not math.isfinite(tolerance) or not 0 < tolerance <= 1e-2:
            raise CalculatorError("Argument ERROR: integral toleransı pozitif sonlu sayı olmalıdır")
        outer_lo = _finite_real_float(outer_lower, "Math ERROR: integral sınırları sonlu reel olmalıdır")
        outer_hi = _finite_real_float(outer_upper, "Math ERROR: integral sınırları sonlu reel olmalıdır")
        integrand = self._numeric_complex_callable(expression, (outer, inner), label="integrand")
        lower = self._numeric_real_callable(inner_lower, (outer,), label="iç integral sınırı")
        upper = self._numeric_real_callable(inner_upper, (outer,), label="iç integral sınırı")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", IntegrationWarning)
                warnings.simplefilter("error", RuntimeWarning)
                real, real_error = dblquad(
                    lambda inner_value, outer_value: float(np.real(integrand(outer_value, inner_value))),
                    outer_lo, outer_hi, lower, upper, epsabs=tolerance, epsrel=tolerance,
                )
                imag, imag_error = dblquad(
                    lambda inner_value, outer_value: float(np.imag(integrand(outer_value, inner_value))),
                    outer_lo, outer_hi, lower, upper, epsabs=tolerance, epsrel=tolerance,
                )
        except CalculatorError:
            raise
        except Exception as exc:
            raise CalculatorError("Math ERROR: karmaşık çift katlı integral hesaplanamadı") from exc
        self._finish_numeric_multivariate(real, real_error)
        self._finish_numeric_multivariate(imag, imag_error)
        return _finite_complex(complex(real, imag), "Math ERROR: karmaşık çift katlı integral sonucu sonlu değil")

    def _numeric_triple_integral(
        self, expression: sp.Expr, outer: sp.Symbol, middle: sp.Symbol, inner: sp.Symbol,
        outer_lower: sp.Expr, outer_upper: sp.Expr,
        middle_lower: sp.Expr, middle_upper: sp.Expr,
        inner_lower: sp.Expr, inner_upper: sp.Expr, *, tol: float,
    ) -> float:
        try:
            tolerance = float(tol)
        except (TypeError, ValueError) as exc:
            raise CalculatorError("Argument ERROR: integral toleransı pozitif sonlu sayı olmalıdır") from exc
        if not math.isfinite(tolerance) or not 0 < tolerance <= 1e-2:
            raise CalculatorError("Argument ERROR: integral toleransı pozitif sonlu sayı olmalıdır")
        outer_lo = _finite_real_float(outer_lower, "Math ERROR: integral sınırları sonlu reel olmalıdır")
        outer_hi = _finite_real_float(outer_upper, "Math ERROR: integral sınırları sonlu reel olmalıdır")
        integrand = self._numeric_real_callable(expression, (outer, middle, inner), label="integrand")
        middle_lo = self._numeric_real_callable(middle_lower, (outer,), label="orta integral sınırı")
        middle_hi = self._numeric_real_callable(middle_upper, (outer,), label="orta integral sınırı")
        inner_lo = self._numeric_real_callable(inner_lower, (outer, middle), label="iç integral sınırı")
        inner_hi = self._numeric_real_callable(inner_upper, (outer, middle), label="iç integral sınırı")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", IntegrationWarning)
                warnings.simplefilter("error", RuntimeWarning)
                value, error = tplquad(
                    lambda inner_value, middle_value, outer_value: integrand(outer_value, middle_value, inner_value),
                    outer_lo, outer_hi,
                    middle_lo, middle_hi,
                    inner_lo, inner_hi,
                    epsabs=tolerance, epsrel=tolerance,
                )
        except CalculatorError:
            raise
        except Exception as exc:
            raise CalculatorError("Math ERROR: üç katlı integral hesaplanamadı") from exc
        return self._finish_numeric_multivariate(value, error)

    def _commit_multivariate_integral(self, expression: str, result: float) -> None:
        self.ans = sp.Float(result)
        self._remember_history(expression, self.format_result(result, approximate=True))

    def double_integral(
        self, integrand: str,
        outer_lower: str, outer_upper: str, inner_lower: str, inner_upper: str,
        outer_variable: str = "x", inner_variable: str = "y", tol: float = 1e-8,
    ) -> float:
        """Evaluate ``∫x ∫y f(x,y) dy dx`` over finite, optionally nested bounds."""
        self._validate_distinct_calculus_variables(outer_variable, inner_variable)
        outer, inner = sp.Symbol(outer_variable), sp.Symbol(inner_variable)
        expression = self.parse_symbolic(
            integrand, self._calculus_symbol_locals({outer_variable: outer, inner_variable: inner}),
        )
        if expression.free_symbols - {outer, inner}:
            raise CalculatorError("Math ERROR: çift katlı integralde bilinmeyen değişken var")
        outer_lo = self._parse_finite_multivariate_bound(outer_lower)
        outer_hi = self._parse_finite_multivariate_bound(outer_upper)
        inner_lo = self._parse_finite_multivariate_bound(inner_lower, (outer,))
        inner_hi = self._parse_finite_multivariate_bound(inner_upper, (outer,))
        result = self._try_exact_nested_integral(
            expression, ((outer, outer_lo, outer_hi), (inner, inner_lo, inner_hi)),
        )
        if result is None:
            result = self._numeric_double_integral(
                expression, outer, inner, outer_lo, outer_hi, inner_lo, inner_hi, tol=tol,
            )
        self._commit_multivariate_integral(
            f"∫{outer_lower}→{outer_upper} ∫{inner_lower}→{inner_upper} {integrand} d{inner_variable} d{outer_variable}", result,
        )
        return result

    def complex_double_integral(
        self, integrand: str,
        outer_lower: str, outer_upper: str, inner_lower: str, inner_upper: str,
        outer_variable: str = "x", inner_variable: str = "y", tol: float = 1e-8,
    ):
        """Evaluate a finite nested complex double integral over real bounds."""
        self._validate_distinct_calculus_variables(outer_variable, inner_variable)
        outer, inner = sp.Symbol(outer_variable), sp.Symbol(inner_variable)
        expression = self.parse_symbolic(
            integrand, self._calculus_symbol_locals({outer_variable: outer, inner_variable: inner}),
        )
        if expression.free_symbols - {outer, inner}:
            raise CalculatorError("Math ERROR: karmaşık çift katlı integralde bilinmeyen değişken var")
        outer_lo = self._parse_finite_multivariate_bound(outer_lower)
        outer_hi = self._parse_finite_multivariate_bound(outer_upper)
        inner_lo = self._parse_finite_multivariate_bound(inner_lower, (outer,))
        inner_hi = self._parse_finite_multivariate_bound(inner_upper, (outer,))
        result = self._try_exact_nested_integral(
            expression, ((outer, outer_lo, outer_hi), (inner, inner_lo, inner_hi)), allow_complex=True,
        )
        approximate = result is None
        if result is None:
            result = self._numeric_complex_double_integral(
                expression, outer, inner, outer_lo, outer_hi, inner_lo, inner_hi, tol=tol,
            )
        self._commit_definite_integral(
            f"∫{outer_lower}→{outer_upper} ∫{inner_lower}→{inner_upper} {integrand} d{inner_variable} d{outer_variable}",
            result, approximate=approximate,
        )
        return result

    def triple_integral(
        self, integrand: str,
        outer_lower: str, outer_upper: str,
        middle_lower: str, middle_upper: str,
        inner_lower: str, inner_upper: str,
        outer_variable: str = "x", middle_variable: str = "y", inner_variable: str = "z", tol: float = 1e-7,
    ) -> float:
        """Evaluate ``∫x ∫y ∫z f(x,y,z) dz dy dx`` on finite nested bounds."""
        self._validate_distinct_calculus_variables(outer_variable, middle_variable, inner_variable)
        outer, middle, inner = sp.Symbol(outer_variable), sp.Symbol(middle_variable), sp.Symbol(inner_variable)
        expression = self.parse_symbolic(integrand, self._calculus_symbol_locals({
            outer_variable: outer, middle_variable: middle, inner_variable: inner,
        }))
        if expression.free_symbols - {outer, middle, inner}:
            raise CalculatorError("Math ERROR: üç katlı integralde bilinmeyen değişken var")
        outer_lo = self._parse_finite_multivariate_bound(outer_lower)
        outer_hi = self._parse_finite_multivariate_bound(outer_upper)
        middle_lo = self._parse_finite_multivariate_bound(middle_lower, (outer,))
        middle_hi = self._parse_finite_multivariate_bound(middle_upper, (outer,))
        inner_lo = self._parse_finite_multivariate_bound(inner_lower, (outer, middle))
        inner_hi = self._parse_finite_multivariate_bound(inner_upper, (outer, middle))
        result = self._try_exact_nested_integral(
            expression,
            ((outer, outer_lo, outer_hi), (middle, middle_lo, middle_hi), (inner, inner_lo, inner_hi)),
        )
        if result is None:
            result = self._numeric_triple_integral(
                expression, outer, middle, inner,
                outer_lo, outer_hi, middle_lo, middle_hi, inner_lo, inner_hi, tol=tol,
            )
        self._commit_multivariate_integral(
            f"∫{outer_lower}→{outer_upper} ∫{middle_lower}→{middle_upper} ∫{inner_lower}→{inner_upper} "
            f"{integrand} d{inner_variable} d{middle_variable} d{outer_variable}", result,
        )
        return result

    def _line_path_transform(
        self, path_x: str, path_y: str, lower: str, upper: str, parameter: str,
    ) -> tuple[sp.Symbol, sp.Expr, sp.Expr, sp.Expr, sp.Expr]:
        self._validate_calculus_variable(parameter, label="Yol parametresi")
        t = sp.Symbol(parameter, real=True)
        locals_ = self._calculus_symbol_locals({parameter: t})
        x_path = self.parse_symbolic(path_x, locals_)
        y_path = self.parse_symbolic(path_y, locals_)
        if x_path.free_symbols - {t} or y_path.free_symbols - {t}:
            raise CalculatorError("Math ERROR: yol yalnız parametre değişkenini içermelidir")
        lower_expr = self._parse_finite_multivariate_bound(lower)
        upper_expr = self._parse_finite_multivariate_bound(upper)
        return t, x_path, y_path, lower_expr, upper_expr

    def line_integral(
        self, integrand: str, path_x: str, path_y: str, lower: str, upper: str, parameter: str = "t", tol: float = 1e-10,
    ) -> float:
        """Scalar planar line integral ``∫_C f(x,y) ds`` for ``C=(x(t),y(t))``."""
        t, x_path, y_path, lower_expr, upper_expr = self._line_path_transform(path_x, path_y, lower, upper, parameter)
        x, y = sp.Symbol("x"), sp.Symbol("y")
        field = self.parse_symbolic(integrand, self._calculus_symbol_locals({"x": x, "y": y}))
        if field.free_symbols - {x, y}:
            raise CalculatorError("Math ERROR: çizgisel integral integrandı yalnız x ve y içermelidir")
        try:
            dx = self._run_cas("differentiate", {"expression": x_path, "symbol": t})
            dy = self._run_cas("differentiate", {"expression": y_path, "symbol": t})
            transformed = self._run_cas("simplify", {
                "expression": field.subs({x: x_path, y: y_path}) * sp.sqrt(dx**2 + dy**2),
            })
        except Exception as exc:
            raise CalculatorError("Math ERROR: çizgisel integral hazırlanamadı") from exc
        result, approximate = self._definite_integral_expression(
            transformed, lower_expr, upper_expr, t, tol=tol, allow_complex=False,
        )
        self._commit_definite_integral(
            f"∫C {integrand} ds; ({path_x},{path_y}), {lower}→{upper}", result, approximate=approximate,
        )
        return result

    def vector_line_integral(
        self, component_x: str, component_y: str,
        path_x: str, path_y: str, lower: str, upper: str, parameter: str = "t", tol: float = 1e-10,
    ) -> float:
        """Planar work integral ``∫_C P dx + Q dy`` for a parameterized path."""
        t, x_path, y_path, lower_expr, upper_expr = self._line_path_transform(path_x, path_y, lower, upper, parameter)
        x, y = sp.Symbol("x"), sp.Symbol("y")
        locals_ = self._calculus_symbol_locals({"x": x, "y": y})
        p = self.parse_symbolic(component_x, locals_)
        q = self.parse_symbolic(component_y, locals_)
        if p.free_symbols - {x, y} or q.free_symbols - {x, y}:
            raise CalculatorError("Math ERROR: vektör alanı yalnız x ve y içermelidir")
        try:
            dx = self._run_cas("differentiate", {"expression": x_path, "symbol": t})
            dy = self._run_cas("differentiate", {"expression": y_path, "symbol": t})
            transformed = self._run_cas("simplify", {
                "expression": p.subs({x: x_path, y: y_path}) * dx + q.subs({x: x_path, y: y_path}) * dy,
            })
        except Exception as exc:
            raise CalculatorError("Math ERROR: vektör çizgisel integral hazırlanamadı") from exc
        result, approximate = self._definite_integral_expression(
            transformed, lower_expr, upper_expr, t, tol=tol, allow_complex=False,
        )
        self._commit_definite_integral(
            f"∫C ({component_x})dx+({component_y})dy; ({path_x},{path_y}), {lower}→{upper}", result,
            approximate=approximate,
        )
        return result

    def _surface_transform(
        self, path_x: str, path_y: str, path_z: str,
        outer_variable: str, inner_variable: str,
    ) -> tuple[sp.Symbol, sp.Symbol, sp.Expr, sp.Expr, sp.Expr, sp.Matrix]:
        self._validate_distinct_calculus_variables(outer_variable, inner_variable)
        outer, inner = sp.Symbol(outer_variable), sp.Symbol(inner_variable)
        locals_ = self._calculus_symbol_locals({outer_variable: outer, inner_variable: inner})
        paths = tuple(self.parse_symbolic(value, locals_) for value in (path_x, path_y, path_z))
        if any(path.free_symbols - {outer, inner} for path in paths):
            raise CalculatorError("Math ERROR: yüzey parametreleri yalnız u ve v değişkenlerini içerebilir")
        try:
            r_outer = sp.Matrix([self._run_cas("differentiate", {"expression": path, "symbol": outer}) for path in paths])
            r_inner = sp.Matrix([self._run_cas("differentiate", {"expression": path, "symbol": inner}) for path in paths])
        except Exception as exc:
            raise CalculatorError("Math ERROR: yüzey türevleri hesaplanamadı") from exc
        return outer, inner, paths[0], paths[1], paths[2], r_outer.cross(r_inner)

    def surface_integral(
        self, integrand: str, path_x: str, path_y: str, path_z: str,
        outer_lower: str, outer_upper: str, inner_lower: str, inner_upper: str,
        outer_variable: str = "u", inner_variable: str = "v", tol: float = 1e-8,
    ) -> float:
        """Scalar surface integral ``∫∫_S f(x,y,z) dS`` over a parameterized patch."""
        outer, inner, x_path, y_path, z_path, normal = self._surface_transform(
            path_x, path_y, path_z, outer_variable, inner_variable,
        )
        x, y, z = sp.Symbol("x"), sp.Symbol("y"), sp.Symbol("z")
        field = self.parse_symbolic(integrand, self._calculus_symbol_locals({"x": x, "y": y, "z": z}))
        if field.free_symbols - {x, y, z}:
            raise CalculatorError("Math ERROR: yüzey integrandı yalnız x, y ve z içermelidir")
        metric = sp.sqrt(sum(component**2 for component in normal))
        try:
            transformed = self._run_cas("simplify", {
                "expression": field.subs({x: x_path, y: y_path, z: z_path}) * metric,
            })
        except Exception as exc:
            # Match the other path-based calculus operations: a CAS-side
            # simplification failure is an expected calculation failure, not
            # a controller crash that reaches the desktop as an internal error.
            raise CalculatorError("Math ERROR: surface integral could not be prepared") from exc
        result = self.double_integral(
            str(transformed), outer_lower, outer_upper, inner_lower, inner_upper,
            outer_variable, inner_variable, tol,
        )
        self.history[-1] = (
            f"∫∫S {integrand} dS; r=({path_x},{path_y},{path_z})",
            self.history[-1][1],
        )
        return result

    def surface_flux_integral(
        self, component_x: str, component_y: str, component_z: str,
        path_x: str, path_y: str, path_z: str,
        outer_lower: str, outer_upper: str, inner_lower: str, inner_upper: str,
        outer_variable: str = "u", inner_variable: str = "v", reverse_orientation: bool = False, tol: float = 1e-8,
    ) -> float:
        """Oriented flux ``∫∫_S F·(r_u×r_v) du dv`` over a parameterized patch."""
        if not isinstance(reverse_orientation, bool):
            raise CalculatorError("Argument ERROR: yüzey normali yönü geçersiz")
        outer, inner, x_path, y_path, z_path, normal = self._surface_transform(
            path_x, path_y, path_z, outer_variable, inner_variable,
        )
        if reverse_orientation:
            normal = -normal
        x, y, z = sp.Symbol("x"), sp.Symbol("y"), sp.Symbol("z")
        locals_ = self._calculus_symbol_locals({"x": x, "y": y, "z": z})
        components = tuple(self.parse_symbolic(value, locals_) for value in (component_x, component_y, component_z))
        if any(component.free_symbols - {x, y, z} for component in components):
            raise CalculatorError("Math ERROR: akı alanı yalnız x, y ve z içermelidir")
        field = sp.Matrix([component.subs({x: x_path, y: y_path, z: z_path}) for component in components])
        try:
            transformed = self._run_cas("simplify", {"expression": field.dot(normal)})
        except Exception as exc:
            raise CalculatorError("Math ERROR: surface flux integral could not be prepared") from exc
        result = self.double_integral(
            str(transformed), outer_lower, outer_upper, inner_lower, inner_upper,
            outer_variable, inner_variable, tol,
        )
        orientation = "reverse" if reverse_orientation else f"r_{outer_variable}×r_{inner_variable}"
        self.history[-1] = (
            f"∫∫S F·dS; F=({component_x},{component_y},{component_z}), r=({path_x},{path_y},{path_z}), "
            f"normal={orientation}",
            self.history[-1][1],
        )
        return result

    @classmethod
    def _validate_ode_variables(cls, dependent_variable: str, independent_variable: str) -> None:
        cls._validate_calculus_variable(dependent_variable, label="Bağımlı değişken")
        cls._validate_calculus_variable(independent_variable, label="Bağımsız değişken")
        if dependent_variable == independent_variable:
            raise CalculatorError("Syntax ERROR: bağımlı ve bağımsız değişken farklı olmalıdır")
        if {dependent_variable, independent_variable} & {"d", "e", "i", "I"}:
            raise CalculatorError("Syntax ERROR: ODE değişkeni d, e veya i olamaz")

    def _ode_locals(
        self, independent: sp.Symbol, dependent_function: sp.Expr,
    ) -> dict[str, object]:
        """Create symbolic parser locals without leaking calculator memory."""
        locals_ = self.symbolic_locals()
        locals_.update(self._calculus_symbol_locals({str(independent): independent}))
        locals_.update({
            "ODEVALUE": dependent_function,
            "ODEDERIVATIVEONE": sp.diff(dependent_function, independent),
            "ODEDERIVATIVETWO": sp.diff(dependent_function, independent, 2),
        })
        return locals_

    @staticmethod
    def _ode_replace_derivative_notation(
        equation: str, dependent_variable: str, independent_variable: str,
    ) -> tuple[str, int]:
        """Turn calculator-friendly derivative notation into safe parser markers."""
        dependent = re.escape(dependent_variable)
        independent = re.escape(independent_variable)
        beginning, ending = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"
        text = equation.replace("\u2032", "'").replace("\u2019", "'")
        second_fraction = (
            rf"{beginning}d\s*(?:\^|\*\*)?\s*2\s*{dependent}\s*/\s*"
            rf"d\s*{independent}\s*(?:\^|\*\*)?\s*2{ending}"
        )
        first_fraction = rf"{beginning}d\s*{dependent}\s*/\s*d\s*{independent}{ending}"
        second_prime = rf"{beginning}{dependent}\s*''(?!['A-Za-z0-9])"
        first_prime = rf"{beginning}{dependent}\s*'(?!['A-Za-z0-9])"
        text, second_count = re.subn(second_fraction, "ODEDERIVATIVETWO", text)
        text, second_prime_count = re.subn(second_prime, "ODEDERIVATIVETWO", text)
        text, first_count = re.subn(first_fraction, "ODEDERIVATIVEONE", text)
        text, first_prime_count = re.subn(first_prime, "ODEDERIVATIVEONE", text)
        if "'" in text:
            raise CalculatorError("Syntax ERROR: yalnız birinci ve ikinci dereceden türevler desteklenir")
        unsupported = re.search(
            rf"{beginning}d\s*(?:\^|\*\*)?\s*(?:[3-9]|[1-9]\d+)\s*{dependent}\s*/\s*"
            rf"d\s*{independent}\s*(?:\^|\*\*)?\s*(?:[3-9]|[1-9]\d+){ending}",
            text,
        )
        if unsupported:
            raise CalculatorError("Syntax ERROR: yalnız birinci ve ikinci dereceden ODE desteklenir")
        return text, second_count + second_prime_count + first_count + first_prime_count

    def _parse_ode_equation(
        self, equation: str, dependent_variable: str, independent_variable: str,
    ) -> tuple[sp.Equality, int, sp.Expr, sp.Symbol]:
        self._validate_ode_variables(dependent_variable, independent_variable)
        normalized = self.normalize(equation)
        if normalized.count("=") > 1:
            raise CalculatorError("Syntax ERROR: diferansiyel denklem yalnız bir = içerebilir")
        if re.search(r"\bODE(?:VALUE|DERIVATIVEONE|DERIVATIVETWO)\b", normalized, flags=re.IGNORECASE):
            raise CalculatorError("Syntax ERROR: ODE ayrılmış ifade adını kullanamaz")
        transformed, derivative_count = self._ode_replace_derivative_notation(
            normalized, dependent_variable, independent_variable,
        )
        if derivative_count == 0:
            foreign = re.search(
                rf"(?<![A-Za-z0-9])d\s*{re.escape(dependent_variable)}\s*/\s*d\s*[A-Za-z](?![A-Za-z0-9])",
                transformed,
            )
            if foreign:
                raise CalculatorError("Syntax ERROR: ODE türevi seçilen bağımsız değişkeni kullanmalıdır")
            raise CalculatorError("Syntax ERROR: ODE birinci veya ikinci türev içermelidir")
        dependent = re.escape(dependent_variable)
        transformed = re.sub(
            rf"(?<![A-Za-z0-9]){dependent}(?![A-Za-z0-9])", "ODEVALUE", transformed,
        )
        if "=" in transformed:
            left_text, right_text = transformed.split("=", 1)
            if not left_text.strip() or not right_text.strip():
                raise CalculatorError("Syntax ERROR: ODE denkleminin iki tarafı da gerekli")
        else:
            left_text, right_text = transformed, "0"
        independent = sp.Symbol(independent_variable)
        dependent_function = sp.Function(dependent_variable)(independent)
        locals_ = self._ode_locals(independent, dependent_function)
        left = self._safe_parse(left_text, locals_)
        right = self._safe_parse(right_text, locals_)
        expression = left - right
        derivatives = expression.atoms(sp.Derivative)
        if not derivatives:
            raise CalculatorError("Syntax ERROR: ODE birinci veya ikinci türev içermelidir")
        orders = []
        for derivative in derivatives:
            if derivative.expr != dependent_function or any(symbol != independent for symbol in derivative.variables):
                raise CalculatorError("Syntax ERROR: yalnız seçilen fonksiyonun türevi desteklenir")
            orders.append(len(derivative.variables))
        order = max(orders)
        if order not in {1, 2}:
            raise CalculatorError("Syntax ERROR: yalnız birinci ve ikinci dereceden ODE desteklenir")
        return sp.Eq(left, right, evaluate=False), order, dependent_function, independent

    @staticmethod
    def _ode_initial_key(
        key: object, dependent_variable: str, independent_variable: str,
    ) -> tuple[str, str | None]:
        if not isinstance(key, str):
            raise CalculatorError("Argument ERROR: başlangıç koşulu adı metin olmalıdır")
        compact = key.replace(" ", "").replace("\u2032", "'").replace("\u2019", "'").lower()
        dependent, independent = dependent_variable.lower(), independent_variable.lower()
        if compact in {"x0", f"{independent}0", "point"}:
            return "point", None
        if compact in {"y0", f"{dependent}0", "value"}:
            return "value", None
        if compact in {
            "dy0", f"d{dependent}0", f"d{dependent}/d{independent}0", f"{dependent}'0", "derivative", "slope",
        }:
            return "derivative", None
        value_match = re.fullmatch(rf"{re.escape(dependent)}\((.+)\)", compact)
        if value_match:
            return "value", value_match.group(1)
        derivative_match = re.fullmatch(
            rf"(?:d{re.escape(dependent)}/d{re.escape(independent)}|{re.escape(dependent)}')\((.+)\)", compact,
        )
        if derivative_match:
            return "derivative", derivative_match.group(1)
        raise CalculatorError("Argument ERROR: başlangıç koşulu x0, y0 veya dy0 olmalıdır")

    def _parse_ode_initial_value(self, value: object, locals_: dict[str, object], *, label: str) -> sp.Expr:
        if isinstance(value, bool):
            raise CalculatorError(f"Argument ERROR: {label} geçersiz")
        if isinstance(value, str):
            result = self._safe_parse(value, locals_)
        elif isinstance(value, (sp.Basic, int, float, complex, np.number)):
            result = sp.sympify(value)
        else:
            raise CalculatorError(f"Argument ERROR: {label} metin veya sayı olmalıdır")
        if result.has(sp.oo, -sp.oo, sp.zoo, sp.nan):
            raise CalculatorError(f"Math ERROR: {label} sonlu olmalıdır")
        return result

    @staticmethod
    def _split_ode_initial_condition_entries(text: str) -> list[str]:
        """Split compact conditions without breaking function argument lists.

        Condition pairs are separated by a top-level comma or semicolon, but
        the safe expression grammar also permits function calls such as
        ``log(8,2)``.  Splitting every comma would reject that valid input
        before it reaches the expression parser.
        """
        entries: list[str] = []
        start = 0
        depth = 0
        for index, character in enumerate(text):
            if character == "(":
                depth += 1
            elif character == ")" and depth > 0:
                depth -= 1
            elif character in {",", ";"} and depth == 0:
                entry = text[start:index].strip()
                if entry:
                    entries.append(entry)
                start = index + 1
        entry = text[start:].strip()
        if entry:
            entries.append(entry)
        return entries

    def _ode_initial_conditions(
        self,
        initial_conditions: Mapping[object, object] | str | None,
        *,
        order: int,
        dependent_variable: str,
        independent_variable: str,
        dependent_function: sp.Expr,
        independent: sp.Symbol,
    ) -> tuple[dict[sp.Expr, sp.Expr] | None, str]:
        if initial_conditions is None or (isinstance(initial_conditions, str) and not initial_conditions.strip()):
            return None, ""
        if isinstance(initial_conditions, str):
            pieces = self._split_ode_initial_condition_entries(initial_conditions)
            if not pieces or any("=" not in piece for piece in pieces):
                raise CalculatorError("Argument ERROR: başlangıç koşulları x0=…, y0=… biçiminde olmalıdır")
            entries: list[tuple[object, object]] = [tuple(piece.split("=", 1)) for piece in pieces]
        elif isinstance(initial_conditions, Mapping):
            entries = list(initial_conditions.items())
        else:
            raise CalculatorError("Argument ERROR: başlangıç koşulları metin veya eşleme olmalıdır")
        locals_ = self._ode_locals(independent, dependent_function)
        parsed: dict[str, sp.Expr] = {}
        for raw_key, raw_value in entries:
            key, point_from_key = self._ode_initial_key(raw_key, dependent_variable, independent_variable)
            if key in parsed:
                raise CalculatorError("Argument ERROR: başlangıç koşulu birden fazla verildi")
            parsed[key] = self._parse_ode_initial_value(raw_value, locals_, label=f"başlangıç {key} değeri")
            if point_from_key is not None:
                point = self._parse_ode_initial_value(point_from_key, locals_, label="başlangıç noktası")
                if "point" in parsed and sp.simplify(parsed["point"] - point) != 0:
                    raise CalculatorError("Argument ERROR: başlangıç koşulları farklı noktalara ait")
                parsed["point"] = point
        if {"point", "value"} - set(parsed):
            raise CalculatorError("Argument ERROR: başlangıç koşulları x0 ve y0 birlikte gerektirir")
        if order == 1 and "derivative" in parsed:
            raise CalculatorError("Argument ERROR: birinci dereceden ODE için y'(x0) girilmez")
        if order == 2 and "derivative" not in parsed:
            raise CalculatorError("Argument ERROR: ikinci dereceden ODE için dy0 gereklidir")
        point = parsed["point"]
        _finite_real_float(point, "Math ERROR: başlangıç noktası sonlu reel olmalıdır")
        for key, value in parsed.items():
            if key != "point" and (value.has(independent) or value.has(dependent_function)):
                raise CalculatorError("Math ERROR: başlangıç değeri bağımsız veya bağımlı değişken içeremez")
        conditions = {dependent_function.subs(independent, point): parsed["value"]}
        if order == 2:
            conditions[sp.diff(dependent_function, independent).subs(independent, point)] = parsed["derivative"]
        shown = ", ".join(f"{key}={value}" for key, value in parsed.items())
        return conditions, shown

    def solve_ode(
        self, equation: str, dependent_variable: str = "y", independent_variable: str = "x",
        initial_conditions: Mapping[object, object] | str | None = None,
    ) -> sp.Equality:
        """Solve a scalar first/second-order symbolic ODE with optional initial data.

        Calculator notation accepts ``dy/dx``/``d2y/dx2`` as well as
        ``y'``/``y''``.  Initial data is either a mapping or compact text such
        as ``x0=0, y0=1, dy0=0``.
        """
        ode, order, dependent_function, independent = self._parse_ode_equation(
            equation, dependent_variable, independent_variable,
        )
        conditions, condition_text = self._ode_initial_conditions(
            initial_conditions,
            order=order,
            dependent_variable=dependent_variable,
            independent_variable=independent_variable,
            dependent_function=dependent_function,
            independent=independent,
        )
        try:
            result = self._run_cas("dsolve", {
                "equation": ode, "function": dependent_function, "ics": conditions,
            })
        except Exception as exc:
            raise CalculatorError("Math ERROR: diferansiyel denklem kapalı biçimde çözülemedi") from exc
        if isinstance(result, (list, tuple)):
            if len(result) != 1:
                raise CalculatorError("Math ERROR: diferansiyel denklem tek bir çözüm vermedi")
            result = result[0]
        if not isinstance(result, sp.Equality) or result.has(sp.Integral):
            raise CalculatorError("Math ERROR: diferansiyel denklem kapalı biçimde çözülemedi")
        self.ans = result
        history_expression = f"ODE {equation}; {dependent_variable}({independent_variable})"
        if condition_text:
            history_expression += f"; {condition_text}"
        self._remember_history(history_expression, self.format_result(result))
        return result
