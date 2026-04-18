@echo off
title Остановка Telegram Bot
schtasks /end /tn "TelegramSD_Bot"
if %errorlevel%==0 (echo ✅ Бот остановлен) else (echo ⚠️ Задача уже не активна)
timeout /t 3 >nul
exit