@echo off
rem Builds a standalone, single-file dist\LSBSteganography.exe with PyInstaller.
setlocal
cd /d "%~dp0"

call "%~dp0setup.bat" --no-pause --with-build
if errorlevel 1 goto :fail

echo   Building dist\LSBSteganography.exe ...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --log-level WARN ^
    --onefile --windowed --name LSBSteganography ^
    --icon "%CD%\assets\app.ico" ^
    --collect-all tkinterdnd2 ^
    --paths "%CD%" ^
    --specpath "%CD%\build" ^
    "%CD%\lsb_stego\__main__.py"
if errorlevel 1 goto :fail

echo.
echo   Done: %CD%\dist\LSBSteganography.exe
echo.
if /i not "%~1"=="--no-pause" pause
endlocal & exit /b 0

:fail
echo.
echo   [ERROR] The build failed - see the messages above.
echo.
if /i not "%~1"=="--no-pause" pause
endlocal & exit /b 1
