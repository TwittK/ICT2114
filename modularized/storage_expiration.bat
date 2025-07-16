@echo off
cd /d %~dp0
call venv\Scripts\activate
python "storage_expiration.py"