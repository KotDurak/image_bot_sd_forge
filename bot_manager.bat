@echo off
chcp 65001 >nul
echo ╔══════════════════════════════════════╗
echo ║    Управление Telegram SD Bot        ║
echo ╚══════════════════════════════════════╝
echo [1] ▶️ Запустить бота
echo [2] ⏹️ Остановить бота
echo [3] 📊 Статус и последние запуски
echo [4] 🔄 Перезапустить
echo [0] ❌ Выход
echo.

choice /c 12340 /n /m "Выбери действие: "
set ACTION=%ERRORLEVEL%

if %ACTION%==1 (
    echo 🔹 Запускаю...
    schtasks /run /tn "TelegramSD_Bot" >nul 2>&1
    timeout /t 2 >nul
    goto status
)
if %ACTION%==2 (
    echo 🔹 Останавливаю...
    schtasks /end /tn "TelegramSD_Bot" >nul 2>&1
    echo ✅ Задача завершена.
    pause
    exit
)
if %ACTION%==3 goto status
if %ACTION%==4 (
    echo 🔹 Перезапускаю...
    schtasks /end /tn "TelegramSD_Bot" >nul 2>&1
    timeout /t 3 >nul
    schtasks /run /tn "TelegramSD_Bot" >nul 2>&1
    timeout /t 2 >nul
    goto status
)
if %ACTION%==0 exit

:status
echo.
schtasks /query /tn "TelegramSD_Bot" /v | findstr /i "Статус Последнее время Результат"
echo.
pause