# FastAPI Backend Architecture

This backend serves as the crucial API gateway joining the real-time Python AI Classroom pipeline (`ai-services`) to any standard web frontend (such as Lovable/React). 

## Architecture Map
The API logic is mapped via `ai-services/api/`:
- **Main Server:** `api/main.py`
- **Schemas:** `api/schemas/` enforces Pydantic 2.0 object-oriented typing across the board.
- **Routes:** `api/routes/` divides the logical controllers into decoupled segments connecting safely downward into the `Supabase` layers protecting migrations implicitly.

## How to Start the API

```bash
# Assuming you are in the project root: C:\Users\vaish\OneDrive\Desktop\AI-Classroom-Monitoring
# 1. Activate the environment (on Windows)
.venv\Scripts\activate
# 2. Run Uvicorn targeting the exact Python Module path intelligently
python -m uvicorn ai-services.api.main:app --reload --port 8000
```
This deploys standard endpoints accessible on `localhost:8000`.

## Endpoints Provided

### Monitoring Triggers (Configuration Sync)
- **`GET /api/monitoring/config`**: Displays exactly which AI pipelines (such as `phone_detection_enabled`) are running.
- **`PUT /api/monitoring/config`**: Live-patches active pipelines. Disabling `talking_detection_enabled` gracefully drops audio buffers without shutting down the primary Video tracking mesh.
- **`GET /api/monitoring/status`**: Infers if there's an active video stream analyzing frames securely based natively on active session bindings.

### Data Retrievals
- **`GET /api/health`**: Simple pulse check confirming server initialization successfully mapped `cv2` and dependencies securely.
- **`GET /api/students`**: Arrays all available registrants cleanly.
- **`GET /api/students/{student_id}`**: Retrieves metadata bindings strictly for individual UUIDs.
- **`GET /api/alerts/{session_id}`**: Extracts flagged behavioral violations natively (with optional parameter polling `?status=New`).
- **`GET /api/attendance/{session_id}`**: Collects attendance checks sequentially matching LBPH threshold overrides.

## CORS Configuration
For secure modern interoperability:
Wildcards are blocked on credentials. Expected origins implicitly mapped include `http://localhost:3000`, `5173`, and `8080`.

## Testing Safely
Run `python ai-services/api/test_api.py` natively without running `uvicorn`. The logic bypasses ASGI servers dynamically mapping natively against an isolated `httpx` testing instance!
