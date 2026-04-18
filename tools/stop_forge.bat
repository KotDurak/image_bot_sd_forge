@echo off
title Остановка SDForge
net stop SDForge
if %errorlevel%==0 (echo ✅ Forge корректно остановлен) else (echo ⚠️ Служба уже остановлена или ошибка)
timeout /t 3 >nul
exit