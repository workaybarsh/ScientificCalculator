#!/bin/sh
# The native .pkg installs this small app bundle beside the calculator.  A
# macOS application cannot hook Finder's Trash action, so this is the explicit,
# user-confirmed full uninstall path.
set -eu

app_path='/Applications/Scientific Calculator.app'
uninstaller_path='/Applications/Scientific Calculator Uninstaller.app'
data_path="$HOME/.scientific_calculator/ScientificCalculator"

if ! /usr/bin/osascript -e 'display dialog "Remove Scientific Calculator and all of its settings, history, and diagnostic data?" buttons {"Cancel", "Remove"} default button "Remove" with icon caution'; then
  exit 0
fi

/usr/bin/pkill -x ScientificCalculator 2>/dev/null || true
/bin/rm -rf -- "$data_path"
/bin/rmdir "$HOME/.scientific_calculator" 2>/dev/null || true

# /Applications may require administrator permission.  The command contains
# two fixed application paths only; user-owned data was deleted above as the
# signed-in user rather than as root.
/usr/bin/osascript - "$app_path" "$uninstaller_path" <<'APPLESCRIPT'
on run argv
  do shell script "/bin/rm -rf -- " & quoted form of item 1 of argv & " " & quoted form of item 2 of argv with administrator privileges
  display dialog "Scientific Calculator and all of its data have been removed." buttons {"OK"} default button "OK"
end run
APPLESCRIPT
