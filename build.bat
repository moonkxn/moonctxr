@echo off
REM ============================================================
REM  build.bat  -  Build ctxr_tools.exe for Windows
REM  Run this once from the folder that contains main.py
REM ============================================================

echo Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from https://python.org
    pause & exit /b 1
)

echo Installing / upgrading PyInstaller...
python -m pip install --upgrade pyinstaller pillow

echo.
echo Building ctxr_tools.exe ...
python -m PyInstaller ctxr_tools.spec --clean

if errorlevel 1 (
    echo.
    echo BUILD FAILED - see output above
    pause & exit /b 1
)

echo.
echo ============================================================
echo  Done!  Your binary is at:  dist\ctxr_tools.exe
echo  Double-click it to launch the GUI.
echo  No Python installation required on the target machine.
echo ============================================================
pause
