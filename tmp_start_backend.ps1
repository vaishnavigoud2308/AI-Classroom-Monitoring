$env:PYTHONPATH = 'c:\Users\vaish\OneDrive\Desktop\AI-Classroom-Monitoring\ai-services\api;c:\Users\vaish\OneDrive\Desktop\AI-Classroom-Monitoring\ai-services'
Set-Location 'c:\Users\vaish\OneDrive\Desktop\AI-Classroom-Monitoring\ai-services\api'
& 'c:\Users\vaish\OneDrive\Desktop\AI-Classroom-Monitoring\.venv312\Scripts\python.exe' -m uvicorn main:app --host 127.0.0.1 --port 8001 --log-level info *> 'c:\Users\vaish\OneDrive\Desktop\AI-Classroom-Monitoring\backend_smoke.log'
