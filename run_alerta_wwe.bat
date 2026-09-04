@echo off
setlocal
cd /d "%~dp0"
py ticket_alert.py --gui --interval 60
pause
