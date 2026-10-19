#!/bin/sh
# Start MapTheGap. Double-click it in your file manager and choose "Run" (in GNOME
# Files: right-click > Run as a Program), or run ./MapTheGap_Linux.sh in a terminal.
# Stop it by closing the terminal, with Ctrl-C, or with [quit] in the app.
cd "$(dirname "$0")" || exit 1

for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1 &&
       "$py" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
        "$py" app.py "$@" && exit 0
        if [ -t 0 ]; then
            printf '\nMapTheGap stopped with an error (above). Press Enter to close.'
            read -r _
        fi
        exit 1
    fi
done

msg="MapTheGap needs Python 3.9 or newer. Install it with your package manager (usually the package called python3), then start MapTheGap again."
echo "$msg"
# launched without a terminal, the message would go nowhere - show it on the desktop
if [ ! -t 1 ]; then
    command -v notify-send >/dev/null 2>&1 && notify-send "MapTheGap" "$msg"
fi
exit 1
