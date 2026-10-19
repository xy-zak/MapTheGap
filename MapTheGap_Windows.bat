@echo off
rem Double-click to start MapTheGap. The window that opens is the app: leave it
rem open while you use the map, and close it to stop.
title MapTheGap
cd /d "%~dp0"

rem "py" is the launcher the python.org installer adds. "python" is tried second, and
rem the version check also screens out the Microsoft Store placeholder that only
rem offers to install Python.
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul && set "PY=python"
if not defined PY goto nopython

%PY% app.py %*
if errorlevel 1 (
    echo.
    echo MapTheGap stopped with an error, shown above.
    pause
)
exit /b

:nopython
echo MapTheGap needs Python 3.9 or newer, and none was found.
echo Install it from python.org - the download page is opening now - and keep
echo "py launcher" ticked in the installer. Then double-click MapTheGap_Windows.bat again.
start "" "https://www.python.org/downloads/windows/"
echo.
pause
exit /b 1
