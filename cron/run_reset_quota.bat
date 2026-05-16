@echo off
cd /d "%~dp0.."

REM 🔑 Используем python из venv, а не системный!
C:\bot_for_sd\.venv\Scripts\python.exe -m cron.reset_quota