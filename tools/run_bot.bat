@echo off
title Запуск Telegram Bot
schtasks /run /tn "TelegramSD_Bot"
if %errorlevel%==0 (echo ✅ Задача на запуск отправлена (бот поднимается ~10 сек)) else (echo ❌ Ошибка запуска задачи)
timeout /t 3 >nul
exit