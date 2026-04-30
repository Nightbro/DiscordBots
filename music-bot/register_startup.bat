@echo off
:: Registers the Music bot to start automatically at Windows login.
:: Run this script once as Administrator.

set TASK_NAME=MusicDiscordBot
set VBS_PATH=%~dp0start_silent.vbs

echo Registering "%TASK_NAME%" in Task Scheduler...

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "wscript.exe \"%VBS_PATH%\"" ^
  /sc onlogon ^
  /rl highest ^
  /f

if %errorlevel% equ 0 (
    echo.
    echo Done! The bot will now start automatically when you log in.
    echo.
    echo Other useful commands:
    echo   schtasks /run /tn "%TASK_NAME%"      - start it now
    echo   schtasks /end /tn "%TASK_NAME%"      - stop it
    echo   schtasks /delete /tn "%TASK_NAME%"   - remove from startup
) else (
    echo.
    echo Failed. Make sure you right-clicked and chose "Run as Administrator".
)

pause
