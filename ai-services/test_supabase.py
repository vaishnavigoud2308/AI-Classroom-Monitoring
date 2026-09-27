import sys
import traceback
from config import get_supabase_client

def test_supabase_connection():
    try:
        # 1. Connect to Supabase using the helper
        client = get_supabase_client()
        
        # 2. Query the students table
        # Using a simple select with limit(1) just to verify read access works
        response = client.table("students").select("id").limit(1).execute()
        
        # 3. Print a simple success message
        print("Success! Successfully connected to Supabase.")
        print("Database query to 'students' table executed without errors.")
        
    except Exception as e:
        # 4. Print a clear error message if it fails
        print("ERROR: Failed to connect or query Supabase.")
        print("Please check your .env credentials and ensure your IP is allowed.")
        print("-" * 40)
        print(f"Details: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    test_supabase_connection()
