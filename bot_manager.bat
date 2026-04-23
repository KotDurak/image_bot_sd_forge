@echo off
title Bot Control Panel - my_bot
cd /d "C:\bot_for_sd"

:menu
cls
echo ===================================
echo   🐾 Bot Control Panel (my_bot)
echo ===================================
echo.
echo [1] Start bot
echo [2] Stop bot
echo [3] Restart bot
echo [4] Show logs (last 30 lines)
echo [5] Open monitor (pm2 monit)
echo [6] Show process status
echo [0] Exit
echo.
set /p choice="Select option: "

if "%choice%"=="1" goto start_bot
if "%choice%"=="2" goto stop_bot
if "%choice%"=="3" goto restart_bot
if "%choice%"=="4" goto show_logs
if "%choice%"=="5" goto monitor
if "%choice%"=="6" goto status
if "%choice%"=="0" exit

goto menu

:start_bot
echo [>] Starting my_bot...
pm2 start ecosystem.config.js
pause
goto menu

:stop_bot
echo [>] Stopping my_bot...
pm2 stop my_bot
pause
goto menu

:restart_bot
echo [>] Restarting my_bot...
pm2 restart my_bot
pause
goto menu

:show_logs
echo [>] Showing logs (Press Ctrl+C to exit):
pm2 logs my_bot --lines 30
pause
goto menu

:monitor
echo [>] Opening monitor...
pm2 monit
goto menu

:status
echo [>] Process status:
pm2 list
pause
goto menu