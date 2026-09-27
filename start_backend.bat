@echo off
REM Start FastAPI backend on port 8001 (from project root)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
set PYTHONPATH=%CD%\ai-services\api;%CD%\ai-services
uvicorn main:app --app-dir ai-services\api --host 127.0.0.1 --port 8001 --reload
