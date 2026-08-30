# Scientific Calculator User Guide

> Version 1.0.0

Scientific Calculator is an independent, offline calculation tool for Windows, Linux, and macOS. Its layout takes inspiration from familiar classic scientific calculators; it is not an emulator, firmware clone, or product affiliated with a calculator manufacturer.

The current Graphite calculator, its LCD layout, and its key map are shown in the [Interface Tour](docs/INTERFACE.md). For the correct release package, checksum verification, native installation, portable use, and complete removal, read [Install, run, and remove](docs/INSTALLATION.md) before starting.

## Contents

1. [Install, run, and remove](docs/INSTALLATION.md)
2. [Interface tour](docs/INTERFACE.md)
3. [Quick start](#quick-start)
4. [Input and key conventions](#input-and-key-conventions)
5. [Calculate, calculus, and SOLVE](#calculate-calculus-and-solve)
6. [Result formatting, memory, and history](#result-formatting-memory-and-history)
7. [Calculation modes](#calculation-modes)
8. [Spreadsheet, table, and equations](#spreadsheet-table-and-equations)
9. [Setup, skins, and saved settings](#setup-skins-and-saved-settings)
10. [Errors and troubleshooting](#errors-and-troubleshooting)

---

## Quick start

1. Install or extract the package for your platform, then start the application. It opens in **Calculate** mode.
2. Enter an expression with the on-screen keys or the LCD input field.
3. Press `=` to calculate.
4. Press `MENU` to choose another mode.

Try these expressions first:

| Task | Input | Result |
|---|---|---|
| Arithmetic | `12+8×3` | `36` |
| Power | `2^10` | `1024` |
| Root | `sqrt(144)` | `12` |
| Trigonometry | `sin(π/2)` | `1` in RAD mode |
| Fraction | `1/3+1/6` | `1/2` |
| Implicit multiplication | `2x` | product of `2` and `x` |

The default angle unit is **RAD**. Select **DEG** in SETUP if you expect `sin(90)` to equal `1`.

## Input and key conventions

### SHIFT and ALPHA

- **SHIFT** enables the yellow secondary key labels. For example: `SHIFT + CALC` opens SOLVE, `SHIFT + ∫` opens the derivative template, and `SHIFT + x` opens summation.
- **ALPHA** enables red variables and symbols, including `A`–`F`, `M`, `x`, `y`, and the red equation sign.
- Modifier state is normally consumed after one operation.

### Expression syntax

| Operation | Input |
|---|---|
| Addition / subtraction | `+`, `-` |
| Multiplication / division | `×`, `÷`, `*`, `/` |
| Power | `^` |
| Roots | `sqrt(9)`, `cbrt(8)` |
| Absolute value | `Abs(-5)` |
| Factorial | `factorial(5)` |
| Constants | `π`, `pi`, `e`, `i` |
| Previous result | `Ans` |
| Implicit multiplication | `2x`, `(x+1)(x-1)` |

Use parentheses for functions, for example `sin(π/6)`, `log(100)`, and `ln(e)`. The selected angle unit is applied to trigonometric calculations.

### Editing

- `DEL` removes the character to the left of the cursor.
- `AC` cancels a running calculation immediately. In Calculate and Complex it returns to a cleared display; in every other mode it reopens that mode's own guidance screen. It never clears saved settings.
- Immediately after `=`, the first `▲` restores the submitted expression for editing. After that, `▲` / `▼` browse calculation history; after `AC`, the first `▲` is always the newest saved entry. `MENU` → `History` shows the saved last 10 calculations and complete results directly on the LCD; use `▲` / `▼` to browse, `◀` / `▶` to pan a long row, and `OPTN` to recall its raw expression without recalculating it.
- `SHIFT + AC` / OFF saves settings and closes the application.
- `ON` performs the same normal close-and-reopen cycle as restarting the application manually. It preserves saved Setup/UI settings and does not clear the settings database.

While `Calculating…` is displayed, calculator input is locked. Press `AC` or Escape to cancel the controller-owned calculation immediately. Calculations have a 30-second limit; timed-out and cancelled results are never added to history or `Ans`.

## Calculate, calculus, and SOLVE

### Standard and scientific calculations

Enter an expression and press `=`. Exact forms are kept when possible.

```text
(5/12)+(1/4)  → 2/3
sqrt(2)^2     → 2
sin(π/4)^2    → 1/2
```

Press `SHIFT + =` to evaluate approximately and show a decimal result using the selected number format.

Common functions include `sin`, `cos`, `tan`, inverse and hyperbolic trigonometric functions, `log`, `ln`, `sqrt`, `cbrt`, `Abs`, `factorial`, `nPr`, and `nCr`.

- `SHIFT + ×` opens the `nPr` input dialog.
- `SHIFT + ÷` opens the `nCr` input dialog.
- `SHIFT + 7` opens constants.
- `SHIFT + 8` opens unit conversions.
- `SHIFT + 9` opens reset options.

In SETUP, choose **Legacy CODATA 2010 (compatibility)** to reproduce the original catalogue or **Current CODATA 2022** for the [current NIST-recommended values](https://physics.nist.gov/cuu/Constants/index.html). The constants window always identifies the catalogue currently selected.

### Calculus (`∫`)

In **Calculate** mode, press `∫` to open the LCD-only calculus chooser; no dialog window opens. It contains **Integral**, **Double**, and **Triple**. `SHIFT + ∫` opens the separate derivative template. `SHIFT + OPTN` inserts the visible `∞` bound token.

Choose **Integral** for the familiar on-calculator template:

1. Enter the function.
2. Use `▲` for the upper bound and `▼` for the lower bound.
3. Use `TAB` or `◀` / `▶` to reach the blank field beside `d`, then enter the differential variable.
4. Press `=` to calculate.

Enter both bounds for a definite integral:

```text
∫₀^π sin(x) dx  → 2
```

Convergent improper bounds may be entered as `inf`, `∞`, `-inf`, or `-∞`:

```text
∫₀^∞ exp(-x) dx  → 1
```

The calculator splits known interior singularities before integration. It rejects divergent integrals and never silently reports a Cauchy principal value as an ordinary integral.

Leave both bounds blank for a symbolic result, displayed with `+ C`:

```text
∫ x^2 dx  → x^3/3 + C
```

The multiple-integral templates start with blank bounds and blank `d□` variables. Fill every bound and differential variable before evaluating. An inner bound may be an expression of an outer variable, such as `x`, `x^2`, or `sin(x)`.

### Derivative

`SHIFT + ∫` opens the derivative template: leave its point field blank for a symbolic derivative, or enter a point for a numerical derivative.

```text
d/dx x^3       → 3x^2
d/dx x^2 at x=3 → 6
```

### Summation and SOLVE

- `SHIFT + x` opens the summation dialog. Enter a function, variable, and inclusive start/end values.
- `SHIFT + CALC` opens SOLVE in Calculate mode. Enter an equation such as `x^2-2=0`, select the variable, and provide a starting estimate when requested.

Use simple single-letter variables such as `x`, `y`, or `A`–`F`. If no finite, verifiable root is found, the application reports `Cannot Solve`.

## Result formatting, memory, and history

SETUP provides the following result options:

- **Input / Output:** mathematical or linear notation.
- **Number Format:** `Norm`, `Fix`, or `Sci`.
- **Number Digits:** 0–9 digits.
- **Fraction Result:** simple fraction or mixed fraction.
- **Complex:** rectangular `a+bi` or polar `r∠θ`.
- **Decimal Mark** and **Digit Separator**.

Use `S⇔D` to switch a suitable exact result to decimal form. `SHIFT + S⇔D` switches suitable rational values to mixed-fraction display.

### Memory

- `STO` stores the current result in `A`, `B`, `C`, `D`, `E`, `F`, `M`, `x`, or `y`.
- `SHIFT + STO` opens a list of stored memory values.
- `M+` and `M−` add to or subtract from memory `M`.
- `Ans` inserts the most recent successful result.

Example: calculate `25`, store it in `A`, then evaluate `A×4` to get `100`.

### History

The calculator stores the latest 10 successful calculations—including integrals, derivatives, summations, and SOLVE—and their displayed results locally. Open `MENU` → `History` to show the list on the existing LCD, beginning with the newest entry as `1` and the next-oldest entry as `2`. Each row retains the complete operation, `=`, and result; use `▲` / `▼` to browse, `◀` / `▶` to inspect an overflowing row, `OPTN` to recall the selected expression, and `AC` to return to normal calculation. No separate window opens. **Reset to Defaults** clears this saved history together with Setup settings. In integral input, `sinxcosx` is accepted as `sin(x)×cos(x)`.

## Calculation modes

Open `MENU` to access all modes.

Matrix, Vector, Statistics, Distribution, Spreadsheet, Table, Equation / Function,
Inequality, and Ratio run directly in the calculator LCD; they do not open a
separate workspace window. In these forms, enter the highlighted value and press
`=` to advance or run it, use `▲`/`▼` to change fields or browse results, use
`◀`/`▶` to change a numbered choice or spreadsheet cell, use `OPTN` to restart
with another action, and use `AC` to restart the current form. SETUP remains a
separate settings window opened with `SHIFT + MENU`.

### Complex

Use `i` for the imaginary unit. In Complex mode, `SHIFT + ENG` inserts the polar angle sign `∠`. Choose rectangular or polar output in SETUP.

```text
(1+i)^2  → 2i
3∠(π/2) → its complex equivalent
```

Press `∫` in Complex mode for the LCD-only complex-integral template; it does not use `OPTN` or a dialog. Its integrand and bounds open blank, and its differential is fixed as `dz`. Enter both bounds for a definite complex integral, or leave both blank for a symbolic result with `+ C`. The existing `SHIFT + ∫` derivative key opens the complex derivative template in this mode. Leave its point field blank to receive the derivative function; enter a complex point to evaluate it at that point. History retains the complete integral or derivative expression together with the result.

### Base-N

Base-N is for signed 32-bit integer expressions.

| Key | Base-N action |
|---|---|
| `x²` | DEC (10) |
| `x^` | HEX (16) |
| `log` | BIN (2) |
| `ln` | OCT (8) |

Examples:

```text
HEX: A+1    → B
BIN: 1010+1 → 1011
hFF+b1      → mixed-base expression
```

Explicit prefixes are `h`, `b`, `o`, and `d`. Logical operators such as `and`, `or`, `xor`, `xnor`, and `not` are supported. Decimal values are not valid in this mode.

### Matrix

Define `MatA` through `MatD` with dimensions from 1×1 to 4×4. Enter one complete row at a time and press `=` to commit it. Within a row, spaces, commas, semicolons, `+`, and a minus sign separate values: `1+2+3` enters `1, 2, 3`; `1-2+3` enters `1, -2, 3`; and `-1-1-1` enters `-1, -1, -1`. The upper keyboard's `-` and the calculator/numpad `−` are both accepted, including after a scientific-notation exponent. The LCD form supports addition, subtraction, multiplication, determinant, inverse, transpose, square, cube, and absolute value.

`MatAns` stores the latest matrix result and can be copied into another matrix. Inverse and determinant operations require a square matrix; an inverse also requires a non-singular matrix.

### Vector

Define `VctA` through `VctD` as 2D or 3D vectors. The LCD form asks for each component in order.

Available operations include addition, subtraction, scalar multiplication, dot product, cross product, magnitude, unit vector, and angle between vectors. A zero vector cannot have a unit-vector or angle result.

### Statistics

For **1-Variable** statistics, enter x values separated by spaces, commas, semicolons, or new lines.

```text
1, 2, 3, 4
```

The output includes count, sums, mean, population/sample variance and standard deviation, minimum, maximum, and quartiles.

If **Statistics Frequency** is enabled in SETUP, enter one non-negative integer frequency for each x value in the second field. Regression supports Linear, Quadratic, Logarithmic, e Exponential, ab Exponential, Power, and Inverse models.

### Distribution

The Distribution LCD form provides Normal PD/CD/Inverse Normal, Binomial PD/CD, and Poisson PD/CD.

- Normal distribution requires a positive `sigma`.
- Binomial `N` and `x` must be non-negative integers; `p` must be between 0 and 1.
- Poisson `lambda` cannot be negative.

## Spreadsheet, table, and equations

### Spreadsheet

The spreadsheet LCD supports cells `A1:E45`. Use `▲`/`▼` for rows and `◀`/`▶` for columns; type a value or `=` formula into the LCD and press `=` to save.

1. Move to a cell with the arrow keys.
2. Enter a value or a formula beginning with `=`.
3. Press `=` to save the cell; `OPTN` opens the LCD tools.

```text
A1: 10
A2: 20
B1: =A1+A2
```

Tools include Delete, Delete All, Copy & Paste, Cut & Paste, Fill, **Insert reference**, Recalculate, and Free Space. **Insert reference** takes the currently selected source cell, a destination cell, and the formula text before that reference; for example, source `A1` with prefix `=1+` creates `=1+A1` in the destination. With **Spreadsheet Auto Calc** disabled in SETUP, formulas are refreshed only with Recalculate. **Spreadsheet Show Cell** chooses Formula or Value display.

### Table

Table creates a value table for one or two functions.

1. Enter `f(x)` and, if enabled in SETUP, `g(x)`.
2. Enter start, end, and step.
3. Review the generated rows.

Example: `f(x)=x^2`, start `-1`, end `1`, step `0.5`. The step cannot be zero and must move toward the chosen end value.

### Equation / Function, Inequality, and Ratio

- **Equation / Function:** solve simultaneous linear systems with 2–4 unknowns, polynomial roots of degree 2–3, or a symbolic ODE. Polynomial roots use individual `x1`, `x2`, … result rows navigated by `▲` / `▼`. In a simultaneous system, `=` accepts the current complete equation row and opens the next row; after the last row it shows each `x1`, `x2`, … result on its own `▲` / `▼`-browsable row. A 4×4 simultaneous equation and the ODE form use two roomy rows, with `◀` / `▶` moving through every coefficient and right-hand-side square. The ODE form is `□·y'' + □·y' + □·y = □`; fill its four boxes from left to right with expressions such as `1`, `x`, `sin(x)`, or `0`. Long fields show `…` without colliding with neighbouring fields. The supported linear ODE is classified automatically. PDEs, order greater than two, and second-order nonlinear equations are explicitly unsupported. For `x²-5x+6`, use the three polynomial coefficient squares in order: `1`, `-5`, `6`.
- **Inequality:** solve degree 2–4 polynomial inequalities. Supply the coefficients and one of `>`, `<`, `≥`, or `≤`.
- **Ratio:** solve either `A:B=X:D` or `A:B=C:X` from three known values.

## Setup, skins, and saved settings

Open SETUP with `SHIFT + MENU`. Important choices include:

| Setting | Choices |
|---|---|
| Angle Unit | DEG, RAD, GRA |
| Number Format / Digits | Norm, Fix, Sci; 0–9 digits |
| Fraction Result | simple or mixed fraction |
| Complex format | rectangular or polar |
| Calculator Skin | Graphite, Blue, Pink, White |
| UI Scale | 40%, 50%, 60%, 75%, 100%, 125%, 150%, 200% |
| Spreadsheet / Table | automatic calculation, cell display, one/two functions |
| Scientific Constants | Legacy CODATA 2010 (compatibility) or Current CODATA 2022 |

Click **Save** to store settings under the current user's SQLite database. On Windows the normal location is `%LOCALAPPDATA%\ScientificCalculator\settings.db`; when `LOCALAPPDATA` is unavailable, Windows, Linux, and macOS use `~/.scientific_calculator/ScientificCalculator/settings.db`. The same database keeps the last 10 calculation expressions and displayed results. **Clear History** asks for confirmation, then removes only those saved calculations. Closing through the window close button or `SHIFT + AC` also saves the active settings. **Reset to Defaults** clears both saved settings and calculation history, then restores the platform default configuration; it is separate from `ON` restart. The default scale is 100% on every platform; macOS may apply a bounded effective-scale fallback only if completed window geometry cannot fit the skin. Native uninstallers close a running Scientific Calculator process, then remove only the fixed app-data location so a reinstall starts clean. For the macOS full-reset route, open the installed **Scientific Calculator Uninstaller.app**.

Settings and history are saved in one transaction. If saving or resetting fails, the SETUP window remains usable and the LCD reports `Settings ERROR`; it does not claim that the operation succeeded.

At 125% and above, the interface needs more vertical screen space. Choose a scale that fits your display.

## Errors and troubleshooting

Errors are displayed directly on the calculator LCD; calculation, input, and settings errors do not open a separate error popup. The current mode remains active, only the active input is cleared, and `Ans` and History retain their last successful values. Integral and derivative template errors use a compact single line at the lower right of the LCD so the template itself stays stable. All user-facing error text is English, including translated legacy engine errors.

| Message | Meaning and next step |
|---|---|
| `Syntax ERROR` | Check parentheses, function names, and operators. |
| `Math ERROR` | The operation is undefined, out of domain, or non-finite. |
| `Dimension ERROR` | Matrix/vector dimensions or spreadsheet addresses do not match. |
| `Argument ERROR` | A required value, valid range, or correct data type is missing. |
| `Cannot Solve` | No finite, verifiable root was found; try another starting estimate. |
| `Range ERROR` | A table or numeric range is not valid. |

When something does not look right:

1. Confirm that the selected mode is appropriate.
2. Check the angle unit.
3. Check parentheses and function arguments.
4. Press `AC` and enter the expression again.
5. Reset SETUP settings if necessary.

## Privacy and download safety

Normal calculations run offline. The restricted mathematical parser accepts only supported calculation syntax and does not execute Python code or system commands.

Download binaries only from the official GitHub release page. Verify the matching Windows, Linux, or macOS package against `SHA256SUMS.txt` before opening it. The native and portable file names are listed in [Install, run, and remove](docs/INSTALLATION.md).
