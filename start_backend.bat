@echo off
REM Keep FastAPI backend alive on port 8001 (auto-restart on crash)
cd /d "%~dp0"
if exist .venv312\Scripts\activate.bat (
    call .venv312\Scripts\activate.bat
) else (
    call .venv\Scripts\activate.bat
)
set PYTHONPATH=%CD%\ai-services\api;%CD%\ai-services

:loop
echo.
echo [%DATE% %TIME%] Starting AI Classroom backend...
python -m uvicorn main:app --app-dir "%CD%\ai-services\api" --host 127.0.0.1 --port 8001
echo [%DATE% %TIME%] Backend exited. Restarting in 3 seconds...
timeout /t 3 /nobreak >nul
goto loop
