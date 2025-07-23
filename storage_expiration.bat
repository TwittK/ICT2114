@echo off
cd /d %~dp0
call .venv\Scripts\activate
cd modularized
python "storage_expiration.py"