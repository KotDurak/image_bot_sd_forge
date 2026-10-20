@echo off
cd /d "%~dp0.."

REM 🔑 Используем python из venv, а не системный!
D:\image_bot\.venv\Scripts\python.exe -m cron.reset_quota