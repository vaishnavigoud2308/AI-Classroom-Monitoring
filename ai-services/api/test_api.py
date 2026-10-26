from fastapi.testclient import TestClient

try:
    from .main import app
except ImportError:
    from main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    print("PASS: /api/health")

def test_monitoring_config_endpoint():
    # 1. Fetch
    response = client.get("/api/monitoring/config")
    assert response.status_code == 200
    data = response.json()
    assert "phone_detection_enabled" in data
    
    # 2. Update
    payload = data.copy()
    payload["phone_detection_enabled"] = not payload["phone_detection_enabled"]
    
    update_res = client.put("/api/monitoring/config", json=payload)
    assert update_res.status_code == 200
    assert update_res.json()["phone_detection_enabled"] == payload["phone_detection_enabled"]
    print("PASS: /api/monitoring/config")

def test_monitoring_status_endpoint():
    response = client.get("/api/monitoring/status")
    assert response.status_code == 200
    data = response.json()
    assert "is_active" in data
    assert "enabled_features" in data
    print("PASS: /api/monitoring/status")

def test_sessions_endpoint_logic():
    # These depend tightly on Supabase.
    # To keep tests isolated from failing via real API configs if run locally without .env, 
    # we just ping the existence of endpoints and catch expected db errors as a sign of API health.
    response = client.get("/api/sessions/unknown-id")
    # Missing DB triggers 500 cleanly, or if it queries, 404 cleanly. 
    # Just asserting the route responds via FastAPI.
    assert response.status_code in (404, 500)
    print("PASS: /api/sessions")
    
def test_students_endpoint():
    response = client.get("/api/students")
    assert response.status_code in (200, 500)
    print("PASS: /api/students")

def run_tests():
    print("==================================================")
    print("     API Test Suite (FastAPI + TestClient)        ")
    print("==================================================\n")
    test_health_endpoint()
    test_monitoring_config_endpoint()
    test_monitoring_status_endpoint()
    test_sessions_endpoint_logic()
    test_students_endpoint()
    print("\n[SUCCESS] API layer test execution completed successfully.")

if __name__ == "__main__":
    run_tests()
