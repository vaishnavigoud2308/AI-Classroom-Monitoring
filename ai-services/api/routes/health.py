from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def check_health():
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "service": "AI Classroom Monitoring Backend"
    }
