# Scientific Calculator User Guide

> Version 1.0

Scientific Calculator is an independent, offline calculation tool for Windows. Its layout takes inspiration from familiar classic scientific calculators; it is not an emulator, firmware clone, or product affiliated with a calculator manufacturer.

## Contents

1. [Quick start](#quick-start)
2. [Input and key conventions](#input-and-key-conventions)
3. [Calculate, calculus, and SOLVE](#calculate-calculus-and-solve)
4. [Result formatting, memory, and history](#result-formatting-memory-and-history)
5. [Calculation modes](#calculation-modes)
6. [Spreadsheet, table, and equations](#spreadsheet-table-and-equations)
7. [Setup, skins, and saved settings](#setup-skins-and-saved-settings)
8. [Errors and troubleshooting](#errors-and-troubleshooting)

---

## Quick start

1. Start the application. It opens in **Calculate** mode.
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
- `▲` and `▼` move through calculation history in the normal expression field. `MENU` → `History` shows the saved last 10 calculations and results directly on the LCD; use `▲` / `▼` to browse it without opening a separate window.
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

The constants window identifies its values as a **CODATA 2010 legacy compatibility dataset**. The set is retained for compatibility and is not presented as the latest CODATA recommendation.

### Integral

Press `∫` to open the integral template.

1. Enter the function.
2. Use `▲` for the upper bound and `▼` for the lower bound.
3. Use `◀` / `▶` to move between the function and variable fields.
4. Press `=` to calculate.

Enter both bounds for a definite integral:

```text
∫₀^π sin(x) dx  → 2
```

Leave both bounds blank for a symbolic integral, which is displayed with `+ C`:

```text
∫ x^2 dx  → x^3/3 + C
```

### Derivative

Press `SHIFT + ∫` to open the derivative template. Leave the point field blank for a symbolic derivative, or enter a point for a numerical derivative.

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

The calculator stores the latest 10 successful calculations—including integrals, derivatives, summations, and SOLVE—and their displayed results locally. Open `MENU` → `History` to show the list on the existing LCD, beginning with the newest entry as `1` and the next-oldest entry as `2`. Each row keeps the operation, `=`, and result visible; use `▲` / `▼` to browse and `AC` to return to normal calculation. No separate window opens. **Reset to Defaults** clears this saved history together with Setup settings. In integral input, `sinxcosx` is accepted as `sin(x)×cos(x)`.

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

Define `MatA` through `MatD` with dimensions from 1×1 to 4×4. The LCD form supports addition, subtraction, multiplication, determinant, inverse, transpose, square, cube, and absolute value.

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

Tools include Delete, Delete All, Copy & Paste, Cut & Paste, Fill, Recalculate, Grab, and Free Space. With **Spreadsheet Auto Calc** disabled in SETUP, formulas are refreshed only with Recalculate. **Spreadsheet Show Cell** chooses Formula or Value display.

### Table

Table creates a value table for one or two functions.

1. Enter `f(x)` and, if enabled in SETUP, `g(x)`.
2. Enter start, end, and step.
3. Review the generated rows.

Example: `f(x)=x^2`, start `-1`, end `1`, step `0.5`. The step cannot be zero and must move toward the chosen end value.

### Equation / Function, Inequality, and Ratio

- **Equation / Function:** solve simultaneous linear systems with 2–4 unknowns or polynomial roots of degree 2–4. For `x²-5x+6`, enter coefficients `1,-5,6`.
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
| UI Scale | 25%, 50%, 75%, 100%, 125%, 150%, 200% |
| Spreadsheet / Table | automatic calculation, cell display, one/two functions |

Click **Save** to store settings under the current Windows user profile in the app's SQLite database. The same database keeps the last 10 calculation expressions and displayed results. Closing through the window close button or `SHIFT + AC` also saves the active settings. **Reset to Defaults** clears both saved settings and calculation history, then restores the default configuration; it is separate from `ON` restart.

Settings and history are saved in one transaction. If saving or resetting fails, the SETUP window remains usable and the LCD reports `Settings ERROR`; it does not claim that the operation succeeded.

At 125% and above, the interface needs more vertical screen space. Choose a scale that fits your display.

## Errors and troubleshooting

Errors are displayed directly on the calculator LCD; calculation, input, and settings errors do not open a separate error popup. The current mode remains active, only the active input is cleared, and `Ans` and History retain their last successful values.

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

Download binaries only from the official GitHub release page. Verify the EXE or installer against `SHA256SUMS.txt` when available.
