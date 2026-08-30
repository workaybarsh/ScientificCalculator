#!/usr/bin/env bash
# Build a native macOS Installer.app package around a PyInstaller .app bundle.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 VERSION APPLICATION_BUNDLE OUTPUT_PKG" >&2
  exit 64
fi

version="$1"
application_bundle="$2"
output_pkg="$3"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

[[ -d "$application_bundle" ]] || { echo "missing app bundle: $application_bundle" >&2; exit 1; }
install -d "$stage/Applications"
cp -R "$application_bundle" "$stage/Applications/Scientific Calculator.app"

uninstaller="$stage/Applications/Scientific Calculator Uninstaller.app"
install -d "$uninstaller/Contents/MacOS"
install -m 0755 "$root/packaging/macos/uninstall.sh" "$uninstaller/Contents/MacOS/ScientificCalculatorUninstaller"
cat > "$uninstaller/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleDisplayName</key><string>Scientific Calculator Uninstaller</string>
  <key>CFBundleExecutable</key><string>ScientificCalculatorUninstaller</string>
  <key>CFBundleIdentifier</key><string>io.github.workaybarsh.scientificcalculator.uninstaller</string>
  <key>CFBundleName</key><string>Scientific Calculator Uninstaller</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$version</string>
</dict></plist>
EOF

mkdir -p "$(dirname "$output_pkg")"
pkgbuild --root "$stage" --identifier io.github.workaybarsh.scientificcalculator \
  --version "$version" --install-location / "$output_pkg"
