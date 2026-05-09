@echo off
REM Tadium Build Script - Windows
REM Run this to build the EXE

echo ========================================
echo TADIUM - Build Script
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.11 first.
    pause
    exit /b 1
)

echo [1/5] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [2/5] Installing Playwright browsers...
playwright install chromium
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Playwright browsers.
    pause
    exit /b 1
)

echo.
echo [3/5] Cleaning old builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [4/5] Building EXE with PyInstaller...
pyinstaller tadium.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo [5/5] Build complete!
echo.
echo ========================================
echo EXE Location: dist\Tadium\Tadium.exe
echo ========================================
echo.
echo IMPORTANT: Place your .gguf model files in:
echo C:\Tadium\models\
echo.
pause
