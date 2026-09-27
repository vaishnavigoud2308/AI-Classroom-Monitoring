import { useState, useEffect, useRef } from "react";
import {
  getHealthStatus,
  startSession,
  stopSession,
  getMonitoringConfig,
  updateMonitoringConfig,
  getMonitoringStatus,
  getAlerts,
  getAttendance,
  getStudents,
  createStudent,
  updateAlertStatus,
  correctAttendance,
} from "../services/api";
import { useAuth } from "../contexts/AuthContext";

const TOGGLE_KEYS = [
  "attendance_enabled",
  "phone_detection_enabled",
  "talking_detection_enabled",
  "sleeping_detection_enabled",
  "looking_away_detection_enabled",
  "unnecessary_activity_enabled",
] as const;

export default function TeacherDashboard() {
  const { user } = useAuth();
  const [health, setHealth] = useState<any>(null);
  const [session, setSession] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [attendance, setAttendance] = useState<any[]>([]);
  const [students, setStudents] = useState<any[]>([]);
  const [enrollName, setEnrollName] = useState("");
  const [enrollRoll, setEnrollRoll] = useState("");
  const [enrollMsg, setEnrollMsg] = useState<string | null>(null);
  const [enrolling, setEnrolling] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const studentName = (id?: string | null) => {
    if (!id) return "Unknown";
    const s = students.find((x) => x.id === id);
    return s ? `${s.name} (${s.roll_number})` : id.slice(0, 8);
  };

  const refreshStudents = () => getStudents().then(setStudents).catch(console.error);

  useEffect(() => {
    getHealthStatus().then(setHealth).catch(console.error);
    getMonitoringConfig().then(setConfig).catch(console.error);
    getMonitoringStatus().then(setStatus).catch(console.error);
    refreshStudents();
  }, []);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | undefined;
    if (session?.session_id) {
      const tick = () => {
        getAlerts(session.session_id).then(setAlerts).catch(console.error);
        getAttendance(session.session_id).then(setAttendance).catch(console.error);
        getMonitoringStatus().then(setStatus).catch(console.error);
      };
      tick();
      interval = setInterval(tick, 5000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [session]);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const teacherLabel =
    user?.email?.split("@")[0]?.replace(/[._]/g, " ") || "Teacher";

  const handleStartSession = async () => {
    try {
      const res = await startSession(teacherLabel);
      setSession(res);
    } catch (e) {
      console.error(e);
    }
  };

  const handleStopSession = async () => {
    if (!session?.session_id) return;
    try {
      await stopSession(session.session_id);
      setSession(null);
      setAlerts([]);
      setAttendance([]);
    } catch (e) {
      console.error(e);
    }
  };

  const toggleConfig = async (key: string) => {
    if (!config) return;
    const prevConfig = { ...config };
    const updatedConfig = { ...config, [key]: !config[key] };
    setConfig(updatedConfig);
    try {
      const serverUpdated = await updateMonitoringConfig(updatedConfig);
      setConfig(serverUpdated);
    } catch (e) {
      console.error("Failed to update config on server:", e);
      setConfig(prevConfig);
    }
  };

  const startCamera = async () => {
    setEnrollMsg(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraOn(true);
    } catch (e: any) {
      setEnrollMsg(e?.message || "Could not access webcam");
    }
  };

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraOn(false);
  };

  const captureAndEnroll = async () => {
    if (!videoRef.current) return;
    setEnrolling(true);
    setEnrollMsg(null);
    try {
      const video = videoRef.current;
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas unavailable");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const face_image_base64 = canvas.toDataURL("image/jpeg", 0.92);

      await createStudent({
        name: enrollName.trim(),
        roll_number: enrollRoll.trim(),
        face_image_base64,
      });
      setEnrollMsg("Student enrolled and face model retrained.");
      setEnrollName("");
      setEnrollRoll("");
      await refreshStudents();
    } catch (e: any) {
      setEnrollMsg(e?.message || "Enrollment failed");
    } finally {
      setEnrolling(false);
    }
  };

  const handleAlertStatus = async (alertId: string, next: "Reviewed" | "Dismissed") => {
    try {
      await updateAlertStatus(alertId, next);
      if (session?.session_id) {
        setAlerts(await getAlerts(session.session_id));
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleAttendanceCorrect = async (
    attendanceId: string,
    next: "Present" | "Absent" | "Late"
  ) => {
    try {
      await correctAttendance(attendanceId, next);
      if (session?.session_id) {
        setAttendance(await getAttendance(session.session_id));
      }
    } catch (e) {
      console.error(e);
    }
  };

  const activeAlerts = alerts.filter((a) => a.status === "New");

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <h1 className="text-3xl font-bold text-slate-800">Teacher Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
          <h2 className="text-xl font-semibold mb-4">System Status</h2>
          <div className="space-y-2">
            <p>
              API Health:{" "}
              <span className={health ? "text-green-600 font-medium" : "text-red-600"}>
                {health ? "Online" : "Offline"}
              </span>
            </p>
            <p>
              Monitoring:{" "}
              <span className={status?.is_active ? "text-green-600 font-medium" : "text-slate-500"}>
                {status?.is_active ? "Active" : "Inactive"}
              </span>
            </p>
            <p>
              Active Session:{" "}
              {session ? (
                <span className="text-blue-600 font-medium break-all">{session.session_id}</span>
              ) : (
                "None"
              )}
            </p>
          </div>
          <div className="mt-6 space-x-4">
            {!session ? (
              <button
                onClick={handleStartSession}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Start Session
              </button>
            ) : (
              <button
                onClick={handleStopSession}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
              >
                Stop Session
              </button>
            )}
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
          <h2 className="text-xl font-semibold mb-4">AI Pipelines</h2>
          {config ? (
            <div className="space-y-3">
              {TOGGLE_KEYS.map((key) => (
                <div key={key} className="flex items-center justify-between">
                  <span className="capitalize text-sm">{key.replace(/_/g, " ")}</span>
                  <button
                    onClick={() => toggleConfig(key)}
                    className={`w-12 h-6 rounded-full relative transition-colors ${
                      config[key] ? "bg-green-500" : "bg-slate-300"
                    }`}
                  >
                    <div
                      className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                        config[key] ? "left-7" : "left-1"
                      }`}
                    />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500">Loading config...</p>
          )}
        </div>

        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
          <h2 className="text-xl font-semibold mb-4">Class Overview</h2>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-slate-500">Registered Students</p>
              <p className="text-2xl font-bold">{students?.length || 0}</p>
            </div>
            <div>
              <p className="text-sm text-slate-500">Present This Session</p>
              <p className="text-2xl font-bold text-green-600">
                {attendance.filter((a) => a.status === "Present").length}
              </p>
            </div>
            <div>
              <p className="text-sm text-slate-500">New Alerts</p>
              <p className="text-2xl font-bold text-red-600">{activeAlerts.length}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Enrollment */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
        <h2 className="text-xl font-semibold mb-4">Enroll Student (Webcam)</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-3">
            <input
              className="w-full border border-slate-300 rounded-lg px-3 py-2"
              placeholder="Student name"
              value={enrollName}
              onChange={(e) => setEnrollName(e.target.value)}
            />
            <input
              className="w-full border border-slate-300 rounded-lg px-3 py-2"
              placeholder="Roll number"
              value={enrollRoll}
              onChange={(e) => setEnrollRoll(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              {!cameraOn ? (
                <button
                  onClick={startCamera}
                  className="px-4 py-2 bg-slate-800 text-white rounded hover:bg-slate-900"
                >
                  Open Camera
                </button>
              ) : (
                <button
                  onClick={stopCamera}
                  className="px-4 py-2 border border-slate-300 rounded hover:bg-slate-50"
                >
                  Close Camera
                </button>
              )}
              <button
                onClick={captureAndEnroll}
                disabled={!cameraOn || enrolling || !enrollName.trim() || !enrollRoll.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {enrolling ? "Enrolling…" : "Capture & Enroll"}
              </button>
            </div>
            {enrollMsg && <p className="text-sm text-slate-600">{enrollMsg}</p>}
            <ul className="text-sm text-slate-600 space-y-1 max-h-40 overflow-y-auto">
              {students.map((s) => (
                <li key={s.id}>
                  {s.name} — {s.roll_number}
                  {s.face_image_url ? " · face enrolled" : " · no face"}
                </li>
              ))}
            </ul>
          </div>
          <div className="relative bg-slate-900 rounded-xl overflow-hidden aspect-video flex items-center justify-center">
            <video ref={videoRef} muted playsInline className="w-full h-full object-cover" />
            {!cameraOn && <span className="absolute text-slate-400 text-sm">Camera off</span>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 h-96 overflow-y-auto">
          <h2 className="text-xl font-semibold mb-4">Recent Alerts</h2>
          {alerts.length === 0 ? (
            <p className="text-slate-500">No alerts detected.</p>
          ) : (
            <ul className="space-y-3">
              {alerts.map((a) => (
                <li
                  key={a.id}
                  className="p-3 bg-red-50 text-red-900 rounded border border-red-100 space-y-2"
                >
                  <div className="flex justify-between gap-2">
                    <span className="font-medium">{a.alert_type}</span>
                    <span className="text-sm opacity-75">
                      {a.created_at ? new Date(a.created_at).toLocaleTimeString() : ""}
                    </span>
                  </div>
                  <p className="text-xs opacity-80">{studentName(a.student_id)} · {a.status}</p>
                  {a.status === "New" && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleAlertStatus(a.id, "Reviewed")}
                        className="text-xs px-2 py-1 bg-white border border-red-200 rounded"
                      >
                        Review
                      </button>
                      <button
                        onClick={() => handleAlertStatus(a.id, "Dismissed")}
                        className="text-xs px-2 py-1 bg-white border border-red-200 rounded"
                      >
                        Dismiss
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 h-96 overflow-y-auto">
          <h2 className="text-xl font-semibold mb-4">Live Attendance</h2>
          {attendance.length === 0 ? (
            <p className="text-slate-500">No students detected yet.</p>
          ) : (
            <ul className="space-y-3">
              {attendance.map((att) => (
                <li
                  key={att.id}
                  className="p-3 bg-green-50 text-green-900 rounded border border-green-100 flex flex-col gap-2"
                >
                  <div className="flex justify-between items-center gap-2">
                    <span>{studentName(att.student_id)}</span>
                    <span className="text-xs bg-green-200 px-2 py-1 rounded">
                      {att.status}
                      {att.manually_corrected ? " · corrected" : ""}
                      {att.confidence != null ? ` · ${att.confidence}%` : ""}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    {(["Present", "Absent", "Late"] as const).map((st) => (
                      <button
                        key={st}
                        onClick={() => handleAttendanceCorrect(att.id, st)}
                        className="text-xs px-2 py-1 bg-white border border-green-200 rounded"
                      >
                        {st}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
