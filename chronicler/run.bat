@echo off
title Chronicler Discord Bot
color 0C

echo ============================================
echo       Chronicler Discord Bot Launcher
echo ============================================
echo.

:: -- Step 1: Check Python ---------------------
:: fpdf2 and Pillow both require 3.11. Catch it here rather than letting it
:: surface as an opaque pip resolution error several steps later.
echo [1/3] Checking Python version...
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if %errorlevel% neq 0 (
    echo [ERROR] Chronicler needs Python 3.11 or newer.
    python --version
    echo         The PDF and image libraries require it.
    echo         See LINUX_SETUP.md section 6.2 for the options.
    pause
    exit /b 1
)
echo Python version is fine.
echo.

:: -- Step 2: Set up Virtual Environment -------
echo [2/3] Setting up virtual environment...
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment. Is Python installed?
        pause
        exit /b 1
    )
    echo Virtual environment created!
) else (
    echo Virtual environment already exists.
)

call venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip
echo.

echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo Dependencies ready!
echo.

:: -- Step 3: Check .env token -----------------
echo [3/3] Checking configuration...
if not exist ".env" (
    echo [ERROR] .env file not found!
    echo.
    echo  Create a .env file in this folder with:
    echo    DISCORD_TOKEN=your_token_here
    echo    OWNER_ID=your_discord_user_id
    echo.
    pause
    exit /b 1
)
findstr /C:"paste_your_token_here" .env >nul 2>&1
if %errorlevel% equ 0 (
    echo [ERROR] You haven't set your DISCORD_TOKEN in the .env file!
    echo.
    pause
    exit /b 1
)
echo Configuration looks good!
echo.

:run_bot
echo ============================================
echo  Chronicler is starting... (Ctrl+C to stop)
echo ============================================
echo.
python bot.py
echo.
echo ============================================
echo  Bot stopped (exit code: %errorlevel%)
echo ============================================
echo.
echo  [R] Restart bot
echo  [Q] Quit
echo.
set /p choice="  Your choice: "
if /i "%choice%"=="Q" exit /b 0
goto :run_bot
