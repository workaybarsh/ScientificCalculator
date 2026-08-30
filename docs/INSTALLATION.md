# Install, run, and remove Scientific Calculator

Scientific Calculator is distributed as independent platform-and-architecture release tracks. Every release page contains a native system installer where that format is available, a portable package, and one matching checksum list. Download files only from the project's GitHub Releases page and choose the release for both your operating system and processor architecture.

## Choose a release file

| Platform | Release tag | Installer | Portable package |
| --- | --- | --- | --- |
| Windows x64 | `windows-x64-v1.0.0` | `ScientificCalculator_Setup_x64.exe` | `ScientificCalculator-windows-x64.zip` |
| Windows ARM64 | `windows-arm64-v1.0.0` | `ScientificCalculator_Setup_arm64.exe` | `ScientificCalculator-windows-arm64.zip` |
| macOS Intel x64 | `macos-intel-x64-v1.0.0` | `ScientificCalculator_Setup_macos-intel-x64.pkg` | `ScientificCalculator-macos-intel-x64.zip` |
| macOS Apple Silicon | `macos-arm64-v1.0.0` | `ScientificCalculator_Setup_macos-m-series.pkg` | `ScientificCalculator-macos-m-series.zip` |
| Linux — Intel or AMD 64-bit architecture | `linux-x86_64-v1.0.0` | `ScientificCalculator-linux-x86_64.deb` | `ScientificCalculator-linux-x86_64.tar.gz` |
| Linux — ARM 64-bit architecture | `linux-arm64-v1.0.0` | `ScientificCalculator-linux-arm64.deb` | `ScientificCalculator-linux-arm64.tar.gz` |

Every release contains a `SHA256SUMS.txt` file with hashes for the two packages on that release page.

## Verify a download

Compare the displayed hash with the matching line in the release's `SHA256SUMS.txt` before opening a package.

```powershell
# Windows PowerShell
(Get-FileHash .\ScientificCalculator_Setup_x64.exe -Algorithm SHA256).Hash.ToLower()
```

Use the same command with `ScientificCalculator_Setup_arm64.exe` for the Windows ARM64 installer.

```sh
# Linux
sha256sum -c SHA256SUMS.txt
```

```sh
# macOS
shasum -a 256 ScientificCalculator_Setup_macos-m-series.pkg
```

The Windows, Linux, and macOS packages are currently unsigned. macOS packages are also not notarized. Verify the hash first and follow the operating system's normal security guidance; do not bypass a security warning solely because the filename looks familiar. After verifying the checksum on macOS, open the app once with **Control-click → Open**; if macOS still blocks it, choose **Open Anyway** in **System Settings → Privacy & Security**. This is the supported disclosure path for an unsigned build.

## Install

### Windows x64

Run `ScientificCalculator_Setup_x64.exe`. The Setup Wizard lets you accept the MIT licence, choose an installation directory, optionally create a desktop shortcut, and launch the calculator when it completes.

### Windows ARM64

Run `ScientificCalculator_Setup_arm64.exe`. It provides the same Setup Wizard and is for Windows on ARM devices.

### Linux — Intel or AMD 64-bit architecture

On Debian or Ubuntu, install the native package:

```sh
sudo apt install ./ScientificCalculator-linux-x86_64.deb
```

It installs to `/opt/ScientificCalculator` and adds **Scientific Calculator** to the application menu.

### Linux — ARM 64-bit architecture

On Debian or Ubuntu ARM64, install the native package with:

```sh
sudo apt install ./ScientificCalculator-linux-arm64.deb
```

### macOS

Use the package matching the Mac:

- **Intel x64** for Intel Macs.
- **M Series** for Apple Silicon Macs (M1, M2, M3, M4, and later).

Open the matching `.pkg` with the native macOS Installer. Open it after verifying its checksum; it installs the calculator and its dedicated uninstaller into `/Applications`.

## Run the portable package

Portable packages do not create shortcuts or change the operating system. Extract the archive and run the application inside it.

- **Windows:** select `ScientificCalculator-windows-x64.zip` for x64 Windows or `ScientificCalculator-windows-arm64.zip` for Windows ARM64. Extract it and open `ScientificCalculator.exe`.
- **Linux:** select `ScientificCalculator-linux-x86_64.tar.gz` for Intel or AMD 64-bit architecture, or `ScientificCalculator-linux-arm64.tar.gz` for ARM 64-bit architecture. Extract it, enter the extracted `ScientificCalculator` directory, then run `./ScientificCalculator`.
- **macOS:** extract the ZIP and open `ScientificCalculator.app` that it contains. Use the archive matching Intel x64 or M Series as above.

## Remove everything cleanly

Guided Setup Wizards remove the running application first, then remove the calculator's own settings, calculation history, SQLite sidecar files, and diagnostic logs. No unrelated files or settings are targeted.

| Platform | Full-removal action |
| --- | --- |
| Windows | Use **Installed apps** / **Apps & features** to uninstall Scientific Calculator. The uninstaller closes `ScientificCalculator.exe` if it is open. |
| Linux | Run `sudo apt remove scientific-calculator`. Its removal script closes the app, removes its app-owned data, and clears `/opt/ScientificCalculator` so the package can be installed again cleanly. |
| macOS | Open **Scientific Calculator Uninstaller.app** from `/Applications`. It is installed by the `.pkg`; confirm removal when prompted. |

Deleting a portable archive is intentionally not a system uninstall, so it cannot automatically remove settings outside the extracted directory. For a portable installation that should leave no calculator data, use **SETUP → Reset to Defaults**, close the app, delete the extracted directory, and remove the app data directory if it remains:

- Windows: `%LOCALAPPDATA%\ScientificCalculator`, or `%USERPROFILE%\.scientific_calculator\ScientificCalculator` when `LOCALAPPDATA` is unavailable.
- Linux and macOS: `~/.scientific_calculator/ScientificCalculator`.

## First-run scale

The Graphite skin is the default everywhere. Every platform starts at **100%** UI scale. On macOS, a post-layout geometry check may temporarily use a smaller effective scale when the completed client area cannot fit the entire skin. A saved user choice is always preserved; **SETUP → Reset to Defaults** restores the 100% default.

For calculator controls, mode navigation, LCD templates, and examples, see the [interface tour](INTERFACE.md) and the [English](../USER_GUIDE.md) or [Türkçe](../KULLANIM_KILAVUZU.md) user guide.
