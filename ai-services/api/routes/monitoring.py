from fastapi import APIRouter, Depends, HTTPException
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(current_dir)
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from schemas.monitoring import MonitoringConfigSchema, MonitoringStatusSchema  # type: ignore
from dependencies import get_monitoring_config, get_session_manager  # type: ignore

router = APIRouter()

@router.get("/config", response_model=MonitoringConfigSchema)
def get_config(config=Depends(get_monitoring_config)):
    """Provides current state of feature toggles."""
    return MonitoringConfigSchema(
        attendance_enabled=config.attendance_enabled,
        phone_detection_enabled=config.phone_detection_enabled,
        talking_detection_enabled=config.talking_detection_enabled,
        sleeping_detection_enabled=config.sleeping_detection_enabled,
        looking_away_detection_enabled=config.looking_away_detection_enabled,
        unnecessary_activity_enabled=config.unnecessary_activity_enabled
    )

@router.put("/config", response_model=MonitoringConfigSchema)
def update_config(updates: MonitoringConfigSchema, config=Depends(get_monitoring_config)):
    """Dynamically applies toggle states to active monitoring backend."""
    config.attendance_enabled = updates.attendance_enabled
    config.phone_detection_enabled = updates.phone_detection_enabled
    config.talking_detection_enabled = updates.talking_detection_enabled
    config.sleeping_detection_enabled = updates.sleeping_detection_enabled
    config.looking_away_detection_enabled = updates.looking_away_detection_enabled
    config.unnecessary_activity_enabled = updates.unnecessary_activity_enabled
    
    return get_config(config)

@router.get("/status", response_model=MonitoringStatusSchema)
def get_status(
    config=Depends(get_monitoring_config),
    session_manager=Depends(get_session_manager)
):
    """Reflects if the active monitoring pipeline is running."""
    session_id = session_manager.session_id
    
    # We infer activity simply based on whether a session is presently open.
    # A true health status would require a ping from webcam_monitor, but this is a solid MVP state.
    is_active = session_id is not None
    
    features = MonitoringConfigSchema(
        attendance_enabled=config.attendance_enabled,
        phone_detection_enabled=config.phone_detection_enabled,
        talking_detection_enabled=config.talking_detection_enabled,
        sleeping_detection_enabled=config.sleeping_detection_enabled,
        looking_away_detection_enabled=config.looking_away_detection_enabled,
        unnecessary_activity_enabled=config.unnecessary_activity_enabled
    )
    
    return MonitoringStatusSchema(
        is_active=is_active,
        current_session_id=session_id,
        enabled_features=features
    )
