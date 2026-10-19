#!/bin/sh
# Double-click in Finder to start MapTheGap. The window that opens is the app:
# leave it open while you use the map, and close it to stop.
#
# The first time, macOS may refuse to open a file it can't verify. Open
# System Settings > Privacy & Security, scroll down and press "Open Anyway".
cd "$(dirname "$0")" || exit 1

for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1 &&
       "$py" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
        "$py" app.py "$@" && exit 0
        printf '\nMapTheGap stopped with an error (above). Press Enter to close.'
        read -r _
        exit 1
    fi
done

echo "MapTheGap needs Python 3.9 or newer, and none was found."
echo "Install it from python.org (the download page is opening now),"
echo "then double-click MapTheGap_Mac.command again."
open "https://www.python.org/downloads/macos/"
printf '\nPress Enter to close.'
read -r _
exit 1
