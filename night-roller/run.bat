@echo off
title Night Roller Discord Bot
color 0D

echo ============================================
echo       Night Roller Discord Bot Launcher
echo ============================================
echo.

:: -- Step 1: Set up Virtual Environment -------
echo [1/2] Setting up virtual environment...
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

:: -- Step 2: Check .env token -----------------
echo [2/2] Checking configuration...
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
echo  Night Roller is starting... (Ctrl+C to stop)
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
