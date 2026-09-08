@echo off
chcp 65001 >nul
title 🤖 Менеджер Бота (PM2)
color 0A

:menu
cls
echo ========================================
echo   🤖 Менеджер Бота (PM2)
echo ========================================
echo.
echo 1. 🚀 Запустить бота
echo 2. 🛑 Остановить бота
echo 3. 🔄 Перезапустить бота
echo 4. 📊 Статус бота
echo 5. 📜 Посмотреть логи (последние 30 строк)
echo 6. 🧹 Очистить логи PM2
echo 0. 🚪 Выход
echo.
set /p choice="Выбери действие (0-6): "

if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto restart
if "%choice%"=="4" goto status
if "%choice%"=="5" goto logs
if "%choice%"=="6" goto clearlogs
if "%choice%"=="0" exit
goto menu

:start
echo.
echo 🚀 Запускаю бота...
cd /d D:\image_bot
pm2 start ecosystem.config.js
timeout /t 3 >nul
pm2 list
echo.
pause
goto menu

:stop
echo.
echo 🛑 Останавливаю бота...
cd /d D:\image_bot
pm2 stop my_bot
echo.
pause
goto menu

:restart
echo.
echo 🔄 Перезапускаю бота...
cd /d D:\image_bot
pm2 restart my_bot
timeout /t 3 >nul
pm2 list
echo.
pause
goto menu

:status
echo.
echo 📊 Текущий статус процессов:
pm2 list
echo.
pause
goto menu

:logs
echo.
echo 📜 Последние 30 строк логов:
echo ----------------------------------------
pm2 logs my_bot --lines 30 --nostream
echo ----------------------------------------
pause
goto menu

:clearlogs
echo.
echo 🧹 Очищаю логи PM2...
pm2 flush
echo ✅ Готово!
timeout /t 2 >nul
goto menu