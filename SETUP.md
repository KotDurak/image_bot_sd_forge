```markdown
# 📖 Руководство по развёртыванию (Windows 10/11)

> **Проект:** Telegram SD Bot + Stable Diffusion Forge  
> **Железо:** RTX 3050 → RTX 3060 (в пути)  
> **Особенность:** Бот работает через VPN → Forge как служба, Бот через Планировщик

---

## 📁 1. Подготовка окружения

Структура папок:

```text
D:\
├── Forge\                  # Portable SD Forge
│   ├── run.bat
│   ├── run_service.bat     # (создадим ниже)
│   └── SDForge.exe + .xml  # WinSW
└── image_bot\              # Бот
    ├── main.py
    ├── config.py
    ├── .venv\
    ├── bot_manager.bat     # (создадим ниже)
    └── 🔄 Перезапуск.bat   # (создадим ниже)
```

**Перед стартом:**

1. Убедитесь, что установлен Python 3.10 или новее.
2. Создайте виртуальное окружение и установите зависимости:

   ```powershell
   cd D:\image_bot
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Проверьте `config.py`: токен, `ALLOWED_USERS`, `FORGE_URL="http://127.0.0.1:7860"`.

---

## 🎨 2. Stable Diffusion Forge (Windows Service)

### 🔹 2.1. Обёртка `run_service.bat`

Создайте в `D:\Forge\` файл со следующим содержимым:

```batch
@echo off
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
call run.bat
exit /b %ERRORLEVEL%
```

### 🔹 2.2. WinSW установка

1. Скачайте `WinSW-x64.exe` с [релиза](https://github.com/winsw/winsw/releases/latest)
2. Переименуйте его в `SDForge.exe` и положите в `D:\Forge\`

### 🔹 2.3. Конфиг `SDForge.xml`

```xml
<service>
  <id>SDForge</id>
  <name>Stable Diffusion Forge</name>
  <description>Forge API (portable)</description>
  <executable>cmd.exe</executable>
  <arguments>/c run_service.bat</arguments>
  <workingdirectory>D:\Forge</workingdirectory>

  <log mode="roll" sizeThreshold="10485760" keepFiles="5"/>
  <onfailure action="restart" delay="5 sec"/>
  <stopparentprocessfirst>true</stopparentprocessfirst>
</service>
```

### 🔹 2.4. Регистрация службы

Откройте **PowerShell от имени администратора** и выполните:

```powershell
cd D:\Forge
.\SDForge.exe install --username "%USERNAME%" --password "ТВОЙ_ПАРОЛЬ_ОТ_WINDOWS"
net start SDForge
sc query SDForge  # Должно быть STATE: 4 RUNNING
```

> ⚠️ **Важно:** запуск **от своего аккаунта** критичен для доступа к GPU. `Local System` не увидит видеокарту.

---

## 🤖 3. Telegram Bot (Task Scheduler + VPN)

### 🔹 3.1. Создание задачи (GUI)

1. Нажмите `Win + R` → `taskschd.msc` → **Создать задачу...**
2. Вкладка **Общие**:
   - Имя: `TelegramSD_Bot`
   - ✅ `Выполнять с наивысшими правами`
   - ✅ `Выполнять только при входе пользователя` *(важно для VPN!)*
   - Настроить для: `Windows 10/11`
3. Вкладка **Триггеры**:
   - Новый → `При входе в систему` → Задержка: `30 сек` → ✅ Включено
4. Вкладка **Действия**:
   - Программа: `D:\image_bot\.venv\Scripts\python.exe`
   - Аргументы: `main.py`
   - Начальная папка: `D:\image_bot`
5. Вкладка **Параметры**:
   - ✅ `Перезапускать при сбое` → `1 мин`, до `3` раз
   - ✅ `Остановить задачу, если выполняется более:` `00:00:00` (бесконечно)
6. Нажмите `ОК` → введите пароль пользователя.

### 🔹 3.2. Альтернатива (PowerShell, если лень в GUI)

```powershell
$Action = New-ScheduledTaskAction -Execute "D:\image_bot\.venv\Scripts\python.exe" -Argument "main.py" -WorkingDirectory "D:\image_bot"
$Trigger = New-ScheduledTaskTrigger -AtLogOn -Delay (New-TimeSpan -Seconds 30)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName "TelegramSD_Bot" -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal
```

---

## 🔄 4. Утилиты управления

### 📄 `🔄 Перезапуск.bat` (на рабочий стол)

```batch
@echo off
chcp 65001 >nul
title 🔄 Умный перезапуск: Forge + Bot

net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo 🎨 Проверяю Forge...
sc query SDForge | find "RUNNING" >nul 2>&1
if %errorlevel%==0 (net stop SDForge >nul & timeout /t 3 >nul)
net start SDForge >nul & echo ✅ Forge запущен

echo 🤖 Проверяю Бота...
schtasks /query /tn "TelegramSD_Bot" /v /fo list 2>nul | findstr /I "Running" >nul 2>&1
if %errorlevel%==0 (schtasks /end /tn "TelegramSD_Bot" >nul & timeout /t 3 >nul)
schtasks /run /tn "TelegramSD_Bot" >nul & echo ✅ Бот запущен

timeout /t 3 >nul
```

**Настройка ярлыка с правами администратора:**

- ПКМ на файл → `Отправить` → `Рабочий стол (создать ярлык)`
- ПКМ на ярлык → `Свойства` → `Дополнительно` → ✅ `Запуск от имени администратора`

---

## ✅ 5. Проверка после установки

| Компонент | Команда проверки | Ожидаемый результат |
|-----------|------------------|---------------------|
| Forge | `sc query SDForge` | `STATE: 4 RUNNING` |
| Бот | `schtasks /query /tn "TelegramSD_Bot"` | `Status: Running` |
| API | `curl http://127.0.0.1:7860/sdapi/v1/sd-models` | `200 OK` + JSON список моделей |
| Логи Forge | `Get-Content D:\Forge\logs\SDForge.out.log -Tail 10` | `API listening on 127.0.0.1:7860` |
| Логи Бота | `Get-Content D:\image_bot\bot.log -Tail 10` | `🤖 Бот запущен и готов к творчеству!` |

**Финальный тест:** отправьте в Telegram команду:

```
/gen cat sitting on keyboard, cozy lighting
```

---

## 🛠️ 6. Частые проблемы и решения

| Симптом | Причина | Решение |
|---------|---------|---------|
| `UnicodeEncodeError: 'charmap'` | Служба использует `cp1251` | Добавьте `<env name="PYTHONUTF8" value="1"/>` в XML или в Task Scheduler |
| `ConnectError: api.telegram.org` | Служба не видит VPN | Запускайте бота **только** через Планировщик (`Run only when user is logged on`) |
| Forge не стартует | Нет доступа к GPU | В WinSW укажите `<username>` своего аккаунта, не `SYSTEM` |
| Порт 7860 занят | Зависший процесс | `Get-Process -Id (Get-NetTCPConnection -LocalPort 7860).OwningProcess \| Stop-Process` |
| Бот молчит после `/gen` | Очередь/БД заблокированы | Проверьте `bot.log`, убедитесь, что `bot_data.db` не открыт другим процессом |

---

