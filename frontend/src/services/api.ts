const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8001/api";

async function fetchAPI(endpoint: string, options?: RequestInit) {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });
    if (!res.ok) {
      let detail = `API Error: ${res.status}`;
      try {
        const body = await res.json();
        if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return await res.json();
  } catch (error) {
    console.error(`[API] Fetch failed for ${endpoint}:`, error);
    throw error;
  }
}

export async function getHealthStatus() {
  return fetchAPI("/health");
}

export async function startSession(teacher_name = "Demo Teacher") {
  return fetchAPI("/sessions/start", {
    method: "POST",
    body: JSON.stringify({ teacher_name }),
  });
}

export async function stopSession(sessionId: string) {
  return fetchAPI(`/sessions/${sessionId}/stop`, { method: "POST" });
}

export async function getSession(sessionId: string) {
  return fetchAPI(`/sessions/${sessionId}`);
}

export async function cleanupOrphanSessions() {
  return fetchAPI("/sessions/cleanup-orphans", { method: "POST" });
}

export async function getMonitoringConfig() {
  return fetchAPI("/monitoring/config");
}

export async function updateMonitoringConfig(updates: Record<string, boolean>) {
  return fetchAPI("/monitoring/config", {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export async function getMonitoringStatus() {
  return fetchAPI("/monitoring/status");
}

export async function getAlerts(sessionId: string) {
  return fetchAPI(`/alerts/${sessionId}`);
}

export async function updateAlertStatus(alertId: string, status: "New" | "Reviewed" | "Dismissed") {
  return fetchAPI(`/alerts/item/${alertId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function getAttendance(sessionId: string) {
  return fetchAPI(`/attendance/${sessionId}`);
}

export async function correctAttendance(attendanceId: string, status: "Present" | "Absent" | "Late") {
  return fetchAPI(`/attendance/item/${attendanceId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function getStudents() {
  return fetchAPI(`/students`);
}

export async function createStudent(payload: {
  name: string;
  roll_number: string;
  email?: string;
  face_image_base64: string;
}) {
  return fetchAPI(`/students`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function retrainFaces() {
  return fetchAPI(`/students/retrain`, { method: "POST" });
}
