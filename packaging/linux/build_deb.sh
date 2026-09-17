#!/usr/bin/env bash
# Build the native Debian/Ubuntu installer package around a PyInstaller bundle.
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 VERSION APP_DIRECTORY OUTPUT_DEB DEBIAN_ARCHITECTURE" >&2
  exit 64
fi

version="$1"
app_directory="$2"
output_deb="$3"
architecture="$4"
case "$architecture" in
  amd64|arm64) ;;
  *)
    echo "unsupported Debian architecture: $architecture" >&2
    exit 64
    ;;
esac
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

[[ -d "$app_directory" ]] || { echo "missing app bundle: $app_directory" >&2; exit 1; }
install -d "$stage/DEBIAN" "$stage/opt/ScientificCalculator" \
  "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/256x256/apps"
cp -a "$app_directory/." "$stage/opt/ScientificCalculator/"
# hicolor directories must name the icon's real pixel size. The previous
# 480x980 directory matched no size any desktop environment looks for, so
# the icon was installed where nothing would ever find it.
install -m 0644 "$app_directory/icons/scientific-calculator.png" \
  "$stage/usr/share/icons/hicolor/256x256/apps/scientific-calculator.png"

cat > "$stage/DEBIAN/control" <<EOF
Package: scientific-calculator
Version: $version
Section: math
Priority: optional
Architecture: $architecture
Maintainer: workaybarsh
Depends: procps
Description: Scientific Calculator
 Offline scientific calculator with a classic calculator-inspired interface.
EOF

cat > "$stage/usr/share/applications/scientific-calculator.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Scientific Calculator
Comment=Offline scientific calculator
Exec=/opt/ScientificCalculator/ScientificCalculator
Icon=scientific-calculator
Terminal=false
Categories=Education;Science;Math;
EOF

# Package removal is an explicit full reset.  Stop only the calculator process
# and remove only the application-owned persistence path for local accounts.
cat > "$stage/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -eu
if [ "$1" = remove ] || [ "$1" = upgrade ] || [ "$1" = deconfigure ]; then
  pkill -x ScientificCalculator 2>/dev/null || true
fi
EOF
chmod 0755 "$stage/DEBIAN/prerm"

cat > "$stage/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -eu
case "$1" in
  remove|purge)
    rm -rf -- /opt/ScientificCalculator
    for home in /home/* /root; do
      data="$home/.scientific_calculator/ScientificCalculator"
      if [ -d "$data" ]; then
        rm -rf -- "$data"
        rmdir "$home/.scientific_calculator" 2>/dev/null || true
      fi
    done
    ;;
esac
EOF
chmod 0755 "$stage/DEBIAN/postrm"

cat > "$stage/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -eu
if [ "$1" = configure ]; then
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
  fi
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
  fi
fi
EOF
chmod 0755 "$stage/DEBIAN/postinst"

mkdir -p "$(dirname "$output_deb")"
dpkg-deb --build --root-owner-group "$stage" "$output_deb"
