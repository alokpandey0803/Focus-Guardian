@echo off
REM ============================================================
REM  FocusGuardian - build a single shareable Windows .exe
REM  Run this ON WINDOWS, inside this project folder, with
REM  Python 3.10+ installed and on PATH.
REM ============================================================

echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo Building FocusGuardian.exe (this can take a minute or two)...
REM --onefile   : bundles EVERYTHING (Python, your code, all libraries)
REM               into one .exe. That's the file you hand to a friend -
REM               nothing else needed, no Python, no source code visible.
REM --windowed  : no console window is ever created - not on your PC,
REM               not on your friend's. There is no "cmd prompt" to close;
REM               the app opens straight to the GUI and only stops when
REM               you actually exit it (via the in-app dialog or tray menu).
REM --noupx     : skips UPX compression, which lowers the odds of an
REM               antivirus false-positive on the packed binary.
REM --icon      : gives it a real icon instead of the default Python one.
pyinstaller --noconfirm --onefile --windowed --noupx --name FocusGuardian ^
    --icon=icon.ico ^
    --collect-all customtkinter ^
    --collect-all plyer ^
    --collect-all pystray ^
    main.py

echo.
if exist dist\FocusGuardian.exe (
    echo Build complete!
    echo Your shareable app is at: dist\FocusGuardian.exe
    echo This single file is everything - copy or send it anywhere.
) else (
    echo Something went wrong - scroll up for the error.
)
pause
