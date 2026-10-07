@echo off
rem Double-click to start LSB Steganography. The first run sets everything up.
rem You can also drop an image onto this file to open it straight away.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    call "%~dp0setup.bat" --no-pause
    if errorlevel 1 (
        pause
        exit /b 1
    )
)
start "" ".venv\Scripts\pythonw.exe" -m lsb_stego %*
