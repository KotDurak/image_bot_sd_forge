@echo off
title Запуск SDForge
net start SDForge
if %errorlevel%==0 (echo ✅ Forge успешно запущен) else (echo ❌ Ошибка: возможно, уже работает или нужны права админа)
timeout /t 3 >nul
exit