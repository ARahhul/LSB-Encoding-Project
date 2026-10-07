@echo off
rem Prepares everything LSB Steganography needs: Python check, Poetry, .venv,
rem dependencies and a shortcut in this folder. Safe to run again at any time.
rem
rem   setup.bat [--no-pause] [--with-build]
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
rem Keep Poetry away from the Windows credential store (avoids rare hangs).
set "PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring"

set "PAUSE_AT_END=1"
set "GROUPS=dev"
for %%A in (%*) do (
    if /i "%%~A"=="--no-pause" set "PAUSE_AT_END="
    if /i "%%~A"=="--with-build" set "GROUPS=dev,build"
)

echo.
echo   LSB Steganography - environment setup
echo   -------------------------------------

rem ---------------------------------------------------------------- Python
set "PYEXE="
for %%V in (3.12 3.13 3.11 3.10 3.14) do (
    if not defined PYEXE (
        for /f "delims=" %%P in ('py -%%V -c "import sys, tkinter; print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
    )
)
if not defined PYEXE (
    for /f "delims=" %%P in ('python -c "import sys, tkinter; print(sys.executable if sys.version_info >= (3, 10) else '')" 2^>nul') do set "PYEXE=%%P"
)
if not defined PYEXE (
    echo.
    echo   [ERROR] Python 3.10 or newer with Tkinter was not found.
    echo           Install it from https://www.python.org/downloads/
    echo           ^(keep "tcl/tk and IDLE" ticked^), then run setup.bat again.
    goto :fail
)
for /f "usebackq delims=" %%V in (`call "%PYEXE%" -c "import platform; print(platform.python_version())"`) do set "PYVER=%%V"
echo   [1/4] Python !PYVER!  ^(%PYEXE%^)

rem ---------------------------------------------------------------- Poetry
set "POETRY="
for /f "delims=" %%P in ('where poetry 2^>nul') do if not defined POETRY set "POETRY=%%P"
if not defined POETRY if exist "%USERPROFILE%\.local\bin\poetry.exe" set "POETRY=%USERPROFILE%\.local\bin\poetry.exe"
if not defined POETRY if exist "%APPDATA%\Python\Scripts\poetry.exe" set "POETRY=%APPDATA%\Python\Scripts\poetry.exe"
if not defined POETRY (
    echo   [2/4] Poetry not found - installing it with pipx ^(per-user, from PyPI^)...
    "%PYEXE%" -m pip install --user --upgrade --quiet --disable-pip-version-check pipx
    if errorlevel 1 goto :fail
    "%PYEXE%" -m pipx install poetry
    if errorlevel 1 goto :fail
    "%PYEXE%" -m pipx ensurepath >nul 2>&1
    for /f "usebackq delims=" %%B in (`call "%PYEXE%" -m pipx environment --value PIPX_BIN_DIR`) do set "PIPX_BIN=%%B"
    if exist "!PIPX_BIN!\poetry.exe" set "POETRY=!PIPX_BIN!\poetry.exe"
)
if not defined POETRY (
    echo   [ERROR] Poetry was installed but poetry.exe could not be located.
    goto :fail
)
for /f "usebackq delims=" %%V in (`call "%POETRY%" --version`) do set "POETRYVER=%%V"
echo   [2/4] !POETRYVER!

rem ------------------------------------------------------- venv + packages
echo   [3/4] Installing dependencies into .venv ^(groups: main, %GROUPS%^)...
call "%POETRY%" env use "%PYEXE%" >nul
if errorlevel 1 goto :fail
call "%POETRY%" install --with %GROUPS% --no-interaction
if errorlevel 1 goto :fail

rem ------------------------------------------------------ icon + shortcut
echo   [4/4] Creating the "LSB Steganography" shortcut in this folder...
".venv\Scripts\python.exe" -m lsb_stego.gui.icons "assets\app.ico" >nul 2>&1
if errorlevel 1 (
    echo         ^(Skipped: the app icon could not be generated.^)
) else (
    powershell -NoProfile -Command "$d = (Get-Location).Path; $s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'LSB Steganography.lnk')); $s.TargetPath = (Join-Path $d '.venv\Scripts\pythonw.exe'); $s.Arguments = '-m lsb_stego'; $s.WorkingDirectory = $d; $s.IconLocation = (Join-Path $d 'assets\app.ico'); $s.Description = 'Hide text or files inside images'; $s.Save()" >nul 2>&1
    if errorlevel 1 echo         ^(Skipped: the shortcut could not be created.^)
)

echo.
echo   Setup complete. Start the app with "LSB Steganography.bat" or the shortcut.
echo.
if defined PAUSE_AT_END pause
endlocal & exit /b 0

:fail
echo.
echo   [ERROR] Setup did not finish - see the messages above.
echo.
if defined PAUSE_AT_END pause
endlocal & exit /b 1
