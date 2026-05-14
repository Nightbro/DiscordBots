@echo off
title Echo Discord Bot
color 0B

echo ============================================
echo          Echo Discord Bot Launcher
echo ============================================
echo.

:: ── Step 1: Check FFmpeg ─────────────────────
echo [1/3] Checking FFmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo FFmpeg not found. Installing via winget...
    winget install --id Gyan.FFmpeg -e --silent
    if %errorlevel% neq 0 (
        echo [ERROR] FFmpeg installation failed. Please install it manually from https://ffmpeg.org
        pause
        exit /b 1
    )
    echo FFmpeg installed successfully!
    echo Please restart this script so FFmpeg is recognized.
    pause
    exit /b 0
) else (
    echo FFmpeg is already installed.
)
echo.

:: ── Step 2: Set up Virtual Environment ───────
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

:: Activate venv
call venv\Scripts\activate.bat

:: Upgrade pip itself first
echo Upgrading pip...
python -m pip install --upgrade pip
echo.

:: Install/update dependencies
echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
:: Always upgrade yt-dlp — YouTube changes frequently and old versions break silently
pip install -U yt-dlp
echo Dependencies ready!
echo.

:: ── Fix SSL cert issue ────────────────────────
echo Fixing SSL certificates...
for /f "delims=" %%i in ('python -c "import certifi; print(certifi.where())"') do set SSL_CERT_FILE=%%i
set REQUESTS_CA_BUNDLE=%SSL_CERT_FILE%
echo SSL_CERT_FILE set to: %SSL_CERT_FILE%
echo.

:: ── Step 3: Check .env token ──────────────────
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
    echo  Open the .env file and replace:
    echo    DISCORD_TOKEN=paste_your_token_here
    echo  with your actual bot token from:
    echo    https://discord.com/developers/applications
    echo.
    pause
    exit /b 1
)
echo Configuration looks good!
echo.

:: ── Run loop ───────────────────────────────────
:run_bot
echo ============================================
echo  Bot is starting...
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
if /i "%choice%"=="R" goto :run_bot
if /i "%choice%"=="Q" exit /b 0
:: Default to restart on any other input
goto :run_bot
