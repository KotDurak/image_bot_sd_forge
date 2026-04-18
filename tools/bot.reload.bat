@echo off
chcp 65001 >nul
title 🔄 Умный перезапуск: Forge + Bot

:: 🔑 Проверка прав администратора (нужны для net start/stop)
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ⚠️ Требуются права администратора для управления службой Forge.
    echo 🔄 Перезапускаю с повышенными правами...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ╔══════════════════════════════════════════╗
echo ║   🔄 Умный перезапуск: Forge + Telegram  ║
echo ╚══════════════════════════════════════════╝
echo.

:: ───────── 1. Stable Diffusion Forge (Windows Service) ─────────
echo 🎨 [1/2] Проверяю Stable Diffusion Forge...
sc query SDForge | find "RUNNING" >nul 2>&1
if %errorlevel%==0 (
    echo    ⚙️  Forge работает → останавливаю...
    net stop SDForge >nul 2>&1
    timeout /t 3 >nul
    echo    ⏹️  Остановлен.
) else (
    echo    ℹ️  Forge не запущен.
)
echo    🚀 Запускаю Forge...
net start SDForge >nul 2>&1
if %errorlevel%==0 (echo    ✅ Forge успешно запущен!) else echo    ❌ Ошибка запуска Forge

echo.

:: ───────── 2. Telegram Bot (Task Scheduler) ─────────
echo 🤖 [2/2] Проверяю Telegram Bot...
schtasks /query /tn "TelegramSD_Bot" /v /fo list 2>nul | findstr /I "Running" >nul 2>&1
if %errorlevel%==0 (
    echo    ⚙️  Бот работает → останавливаю...
    schtasks /end /tn "TelegramSD_Bot" >nul 2>&1
    timeout /t 3 >nul
    echo    ⏹️  Остановлен.
) else (
    echo    ℹ️  Бот не запущен.
)
echo    🚀 Запускаю Бота...
schtasks /run /tn "TelegramSD_Bot" >nul 2>&1
if %errorlevel%==0 (echo    ✅ Бот успешно запущен!) else echo    ❌ Ошибка запуска бота

echo.
echo 🐾 Готово! Барсик и Пушок готовы к работе.
timeout /t 4 >nul
exit
timeout /t 2 >nul
echo.
powershell -Command "[console]::Beep(800,200); [console]::Beep(1000,300)"