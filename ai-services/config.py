import os
from dotenv import load_dotenv
from supabase import create_client, Client

# This script lives inside ai-services/
# The .env file is located at the project root, so we resolve the path accordingly.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, '.env')

load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

def get_supabase_client() -> Client:
    """
    Helper function to initialize and return the Supabase client.
    Can be imported and used by all AI services.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in environment variables.")
        
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
