import os
import sys

# Ensure parent directory is heavily integrated so we can access config.py natively.
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
    
from config import get_supabase_client # type: ignore
from session_manager import MonitoringSessionManager # type: ignore
from monitoring_config import MonitoringConfig # type: ignore

# Global Instances for active backend runtime state (Singletons style)
# Supabase client is fetched per request efficiently without reinstantiating connections repeatedly.
def get_db():
    """Dependency injection wrapper around Supabase Client"""
    return get_supabase_client()

# In a real deployed app, configurations might be saved to a database. 
# Here we keep them loaded in memory matching the existing project footprint.
GLOBAL_CONFIG = MonitoringConfig()

def get_monitoring_config():
    """Dependency injection yielding active system configuration."""
    return GLOBAL_CONFIG

# Session manager to retrieve live pipelines
GLOBAL_SESSION_MANAGER = MonitoringSessionManager()

def get_session_manager():
    """Dependency injection yielding the active MonitoringSessionManager"""
    return GLOBAL_SESSION_MANAGER
