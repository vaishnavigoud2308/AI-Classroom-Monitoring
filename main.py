"""
Root entry point for Uvicorn / Render / Cloud deployments.
This exposes the core FastAPI application defined in ai-services/api/main.py.
"""
import os
import sys

# Compute project root and submodule directories
root_dir = os.path.dirname(os.path.abspath(__file__))
ai_services_dir = os.path.join(root_dir, "ai-services")
api_dir = os.path.join(ai_services_dir, "api")
att_mon_dir = os.path.join(ai_services_dir, "attention-monitoring")
alert_dir = os.path.join(ai_services_dir, "alert-engine")
audio_dir = os.path.join(ai_services_dir, "audio-monitoring")
face_dir = os.path.join(ai_services_dir, "face-recognition")

# Ensure all AI service submodules are in sys.path
for p in (api_dir, ai_services_dir, att_mon_dir, alert_dir, audio_dir, face_dir, root_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

# Load the FastAPI app from ai-services/api/main.py
try:
    # Directly import from ai-services/api/main.py (api_dir is at index 0 of sys.path)
    import importlib.util
    main_py_path = os.path.join(api_dir, "main.py")
    spec = importlib.util.spec_from_file_location("api_main", main_py_path)
    api_main = importlib.util.module_from_spec(spec)
    sys.modules["api_main"] = api_main
    spec.loader.exec_module(api_main)
    app = getattr(api_main, "app")
except Exception:
    import importlib
    mod = importlib.import_module("ai-services.api.main")
    app = getattr(mod, "app")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port)
