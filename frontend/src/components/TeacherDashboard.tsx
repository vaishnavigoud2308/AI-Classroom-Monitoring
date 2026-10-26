import { useState, useEffect, useRef } from "react";
import {
  getHealthStatus,
  startSession,
  stopSession,
  getMonitoringConfig,
  updateMonitoringConfig,
  getMonitoringStatus,
  getAlerts,
  getStudents,
  createStudent,
  updateAlertStatus,
  getAttendanceRoster,
  upsertStudentAttendance,
  submitAttendance,
  getLiveStreamUrl,
  getStudentFaceUrl,
  startAudioMonitoring,
  stopAudioMonitoring,
} from "../services/api";
import { useAuth } from "../contexts/AuthContext";

const TOGGLE_KEYS = [
  "attendance_enabled",
  "phone_detection_enabled",
  "talking_detection_enabled",
  "audio_monitoring_enabled",
  "sleeping_detection_enabled",
  "looking_away_detection_enabled",
  "unnecessary_activity_enabled",
] as const;

type Roster = {
  session_id: string;
  phase: string;
  registered: number;
  present: number;
  not_yet_detected: number;
  absent: number;
  finalized?: boolean;
  students: Array<{
    student_id: string;
    name: string;
    roll_number: string;
    status: string;
    attendance_id: string | null;
    confidence?: number | null;
    manually_corrected?: boolean;
  }>;
};

function cameraLabel(status?: string) {
  switch (status) {
    case "starting":
      return "Camera Starting";
    case "active":
      return "Camera Active";
    case "error":
      return "Camera Error";
    default:
      return "Camera Stopped";
  }
}

export default function TeacherDashboard() {
  const { user } = useAuth();
  const [health, setHealth] = useState<any>(null);
  const [session, setSession] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [roster, setRoster] = useState<Roster | null>(null);
  const [students, setStudents] = useState<any[]>([]);
  const [phase, setPhase] = useState<"idle" | "live" | "review" | "submitted">("idle");
  const [sessionMsg, setSessionMsg] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [enrollName, setEnrollName] = useState("");
  const [enrollRoll, setEnrollRoll] = useState("");
  const [enrollMsg, setEnrollMsg] = useState<string | null>(null);
  const [enrolling, setEnrolling] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const refreshStudents = () => getStudents().then(setStudents).catch(console.error);

  const stopEnrollmentCamera = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraOn(false);
  };

  useEffect(() => {
    getHealthStatus().then(setHealth).catch(console.error);
    getMonitoringConfig().then(setConfig).catch(console.error);
    getMonitoringStatus().then(setStatus).catch(console.error);
    refreshStudents();
  }, []);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | undefined;
    if (session?.session_id && phase === "live") {
      const tick = () => {
        getAlerts(session.session_id).then(setAlerts).catch(console.error);
        getAttendanceRoster(session.session_id, "live").then(setRoster).catch(console.error);
        getMonitoringStatus()
          .then((s) => {
            setStatus(s);
            setHealth({ status: "ok" });
            setSessionError(null);
          })
          .catch(console.error);
      };
      tick();
      interval = setInterval(tick, 2000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [session, phase]);

  useEffect(() => {
    return () => stopEnrollmentCamera();
  }, []);

  const teacherLabel =
    user?.email?.split("@")[0]?.replace(/[._]/g, " ") || "Teacher";

  const handleStartSession = async () => {
    setBusy(true);
    setSessionError(null);
    setSessionMsg(null);
    // Free the webcam from browser enrollment before OpenCV opens it
    stopEnrollmentCamera();
    try {
      const res = await startSession(teacherLabel);
      setSession(res);
      setPhase("live");
      setSessionMsg(res.message || "Live classroom session started.");
      setStatus(await getMonitoringStatus());
      setRoster(await getAttendanceRoster(res.session_id, "live"));
      setAlerts([]);
    } catch (e: any) {
      setSessionError(e?.message || "Failed to start session");
      setPhase("idle");
      setSession(null);
    } finally {
      setBusy(false);
    }
  };

  const handleStopSession = async () => {
    if (!session?.session_id) return;
    setBusy(true);
    setSessionError(null);
    try {
      const res = await stopSession(session.session_id);
      setPhase("review");
      setSessionMsg(res.message || "Session stopped. Review attendance.");
      setRoster(res.review || (await getAttendanceRoster(session.session_id, "review")));
      setStatus(await getMonitoringStatus());
      setAlerts(await getAlerts(session.session_id).catch(() => []));
    } catch (e: any) {
      setSessionError(e?.message || "Failed to stop session");
    } finally {
      setBusy(false);
    }
  };

  const handleEditAttendance = async (studentId: string, next: "Present" | "Absent") => {
    if (!session?.session_id || phase === "submitted") return;
    try {
      await upsertStudentAttendance(session.session_id, studentId, next);
      setRoster(await getAttendanceRoster(session.session_id, "review"));
    } catch (e: any) {
      setSessionError(e?.message || "Could not update attendance");
    }
  };

  const handleSubmitAttendance = async () => {
    if (!session?.session_id || phase === "submitted") return;
    setBusy(true);
    setSessionError(null);
    try {
      const res = await submitAttendance(session.session_id, user?.email || undefined);
      setPhase("submitted");
      setSessionMsg(res.message || "Attendance Submitted");
      setRoster(res.review || (await getAttendanceRoster(session.session_id, "review")));
    } catch (e: any) {
      setSessionError(e?.message || "Submit failed");
    } finally {
      setBusy(false);
    }
  };

  const handleNewSession = () => {
    setSession(null);
    setRoster(null);
    setAlerts([]);
    setPhase("idle");
    setSessionMsg(null);
    setSessionError(null);
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

  const handleToggleAudio = async () => {
    try {
      if (status?.audio_status === "active") {
        await stopAudioMonitoring();
      } else {
        await startAudioMonitoring();
      }
      const updatedStatus = await getMonitoringStatus();
      setStatus(updatedStatus);
    } catch (e: any) {
      console.error("Audio toggle failed:", e);
    }
  };

  const startCamera = async () => {
    setEnrollMsg(null);
    if (phase === "live") {
      setEnrollMsg("Stop the live classroom session before using enrollment camera.");
      return;
    }
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

  const camStatus = status?.camera_status || "stopped";
  const activeAlerts = alerts.filter((a) => a.status === "New");

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <h1 className="text-3xl font-bold text-slate-800">Teacher Dashboard</h1>

      {(sessionMsg || sessionError) && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            sessionError
              ? "border-red-200 bg-red-50 text-red-800"
              : "border-emerald-200 bg-emerald-50 text-emerald-800"
          }`}
        >
          {sessionError || sessionMsg}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Session */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
          <h2 className="text-xl font-semibold mb-4">Session</h2>
          <div className="space-y-2 text-sm">
            <p>
              API:{" "}
              <span className={health ? "text-green-600 font-medium" : "text-red-600"}>
                {health ? "Online" : "Offline"}
              </span>
            </p>
            <p>
              Monitoring:{" "}
              <span className={status?.is_active ? "text-green-600 font-medium" : "text-slate-500"}>
                {status?.is_active ? "ACTIVE" : "Inactive"}
              </span>
            </p>
            <p>
              Camera:{" "}
              <span
                className={
                  camStatus === "active"
                    ? "text-green-600 font-medium"
                    : camStatus === "error"
                      ? "text-red-600 font-medium"
                      : "text-slate-600"
                }
              >
                {cameraLabel(camStatus)}
              </span>
            </p>
            <div className="flex items-center justify-between">
              <p>
                Audio:{" "}
                <span
                  className={
                    status?.audio_status === "active"
                      ? "text-green-600 font-medium"
                      : status?.audio_status === "starting"
                        ? "text-blue-600 font-medium"
                        : status?.audio_status === "error" || status?.audio_status === "unavailable"
                          ? "text-amber-600 font-medium"
                          : "text-slate-600"
                  }
                >
                  {status?.audio_status === "active"
                    ? "Audio Active"
                    : status?.audio_status === "starting"
                      ? "Starting Mic…"
                      : status?.audio_status === "unavailable"
                        ? "Mic Unavailable"
                        : status?.audio_status === "disabled"
                          ? "Audio Disabled"
                          : status?.audio_status === "error"
                            ? "Audio Error"
                            : "Audio Stopped"}
                </span>
                {status?.audio_status === "active" && status?.smoothed_sound_level_db != null && (
                  <span className="text-xs text-slate-500 ml-1">
                    ({Math.round(status.smoothed_sound_level_db)} dB)
                  </span>
                )}
              </p>
              {phase === "live" && (
                <button
                  type="button"
                  onClick={handleToggleAudio}
                  className="text-xs px-2 py-0.5 rounded border border-slate-300 hover:bg-slate-50 text-slate-700 font-medium"
                >
                  {status?.audio_status === "active" ? "Mute Mic" : "Enable Mic"}
                </button>
              )}
            </div>
            {status?.audio_error && (
              <p className="text-amber-600 text-xs">{status.audio_error}</p>
            )}
            {status?.frames_processed != null && phase === "live" && (
              <p className="text-slate-500">Frames processed: {status.frames_processed}</p>
            )}
            <p className="break-all">
              Session:{" "}
              {session?.session_id ? (
                <span className="text-blue-600 font-medium">{session.session_id}</span>
              ) : (
                "None"
              )}
            </p>
            {status?.camera_error && (
              <p className="text-red-600 text-xs">{status.camera_error}</p>
            )}
          </div>
          <div className="mt-6 flex flex-wrap gap-2">
            {phase === "idle" && (
              <button
                onClick={handleStartSession}
                disabled={busy}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {busy ? "Starting…" : "Start Session"}
              </button>
            )}
            {phase === "live" && (
              <button
                onClick={handleStopSession}
                disabled={busy}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
              >
                {busy ? "Stopping…" : "Stop Session"}
              </button>
            )}
            {(phase === "review" || phase === "submitted") && (
              <button
                onClick={handleNewSession}
                className="px-4 py-2 border border-slate-300 rounded hover:bg-slate-50"
              >
                New Session
              </button>
            )}
          </div>
        </div>

        {/* Toggles */}
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

        {/* Overview */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
          <h2 className="text-xl font-semibold mb-4">Class Overview</h2>
          <div className="space-y-3">
            <div>
              <p className="text-sm text-slate-500">Registered Students</p>
              <p className="text-2xl font-bold">{roster?.registered ?? students.length}</p>
            </div>
            <div>
              <p className="text-sm text-slate-500">Present</p>
              <p className="text-2xl font-bold text-green-600">{roster?.present ?? 0}</p>
            </div>
            {phase === "live" ? (
              <div>
                <p className="text-sm text-slate-500">Not Yet Detected</p>
                <p className="text-2xl font-bold text-amber-600">
                  {roster?.not_yet_detected ?? 0}
                </p>
              </div>
            ) : (
              <div>
                <p className="text-sm text-slate-500">Absent</p>
                <p className="text-2xl font-bold text-red-600">{roster?.absent ?? 0}</p>
              </div>
            )}
            <div>
              <p className="text-sm text-slate-500">New Alerts</p>
              <p className="text-2xl font-bold text-red-600">{activeAlerts.length}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Live classroom camera — streams backend OpenCV frames (same camera as recognition) */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
        <h2 className="text-xl font-semibold mb-2">Live Classroom Camera</h2>
        <p className="text-sm text-slate-600 mb-3">
          This preview is the same webcam the backend uses for face recognition and attendance.
          Position your face clearly in the frame. Do not open Enrollment Camera during a live session.
        </p>
        <div className="flex flex-wrap gap-4 text-sm mb-3">
          <span>
            Status: <strong>{cameraLabel(camStatus)}</strong>
          </span>
          <span>
            Monitoring: <strong>{status?.is_monitoring ? "ACTIVE" : "OFF"}</strong>
          </span>
          <span>
            Face model:{" "}
            <strong>{status?.recognizer_trained ? "Trained" : "Not trained"}</strong>
          </span>
          <span>
            Frames: <strong>{status?.frames_processed ?? 0}</strong>
          </span>
          {status?.last_recognized && (
            <span className="text-emerald-700">
              Last match:{" "}
              <strong>
                {status.last_recognized.name} ({status.last_recognized.roll_number}){" "}
                {status.last_recognized.confidence}%
              </strong>
            </span>
          )}
        </div>
        <div className="relative bg-slate-900 rounded-xl overflow-hidden aspect-video flex items-center justify-center">
          {phase === "live" && camStatus === "active" ? (
            <img
              src={getLiveStreamUrl()}
              alt="Live classroom webcam"
              className="w-full h-full object-contain"
            />
          ) : (
            <span className="text-slate-400 text-sm">
              Start Session to open the live classroom webcam preview
            </span>
          )}
        </div>
      </div>

      {/* Attendance */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
        <div className="flex items-center justify-between gap-4 mb-4">
          <h2 className="text-xl font-semibold">
            {phase === "review" || phase === "submitted"
              ? "Review Attendance"
              : "Live Attendance"}
          </h2>
          {phase === "review" && (
            <button
              onClick={handleSubmitAttendance}
              disabled={busy}
              className="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50"
            >
              Submit Attendance
            </button>
          )}
          {phase === "submitted" && (
            <span className="text-emerald-700 font-semibold">Attendance Submitted</span>
          )}
        </div>

        {!roster || roster.students.length === 0 ? (
          <p className="text-slate-500">
            {phase === "idle"
              ? "Start a session to see live attendance."
              : "No registered students yet. Enroll students below."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-2 pr-3">Face</th>
                  <th className="py-2 pr-3">Student</th>
                  <th className="py-2 pr-3">Roll No</th>
                  <th className="py-2 pr-3">Status</th>
                  {(phase === "review" || phase === "submitted") && (
                    <th className="py-2">Action</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {roster.students.map((row) => (
                  <tr key={row.student_id} className="border-b border-slate-100">
                    <td className="py-2 pr-3">
                      <img
                        src={getStudentFaceUrl(row.student_id)}
                        alt={row.name}
                        className="w-10 h-10 rounded object-cover bg-slate-200"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.visibility = "hidden";
                        }}
                      />
                    </td>
                    <td className="py-2 pr-3 font-medium">{row.name}</td>
                    <td className="py-2 pr-3">{row.roll_number}</td>
                    <td className="py-2 pr-3">
                      <span
                        className={
                          row.status === "Present"
                            ? "text-green-700"
                            : row.status === "Absent"
                              ? "text-red-700"
                              : "text-amber-700"
                        }
                      >
                        {row.status}
                      </span>
                      {row.manually_corrected ? " · edited" : ""}
                    </td>
                    {(phase === "review" || phase === "submitted") && (
                      <td className="py-2 space-x-2">
                        {phase === "review" ? (
                          <>
                            <button
                              onClick={() => handleEditAttendance(row.student_id, "Present")}
                              className="text-xs px-2 py-1 border border-slate-300 rounded"
                            >
                              Present
                            </button>
                            <button
                              onClick={() => handleEditAttendance(row.student_id, "Absent")}
                              className="text-xs px-2 py-1 border border-slate-300 rounded"
                            >
                              Absent
                            </button>
                          </>
                        ) : (
                          <span className="text-slate-400 text-xs">Locked</span>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Alerts + Enrollment */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 h-96 overflow-y-auto">
          <h2 className="text-xl font-semibold mb-4">Live Alerts</h2>
          {alerts.length === 0 ? (
            <p className="text-slate-500">No alerts detected.</p>
          ) : (
            <ul className="space-y-3">
              {alerts.map((a) => (
                <li
                  key={a.id}
                  className="p-3 bg-red-50 text-red-900 rounded border border-red-100 space-y-2"
                >
                  <div className="flex justify-between gap-2 items-start">
                    <div>
                      <span className="font-semibold block">
                        {a.alert_type === "excessive_noise"
                          ? "Excessive Classroom Noise"
                          : a.alert_type === "prolonged_discussion"
                            ? "Possible Prolonged Discussion"
                            : a.description || a.alert_type}
                      </span>
                      {a.alert_type === "excessive_noise" && a.confidence != null && (
                        <span className="text-xs text-red-700 block">
                          Sound Level: {Math.round(a.confidence)} dB
                        </span>
                      )}
                      {a.alert_type === "prolonged_discussion" && (
                        <span className="text-xs text-amber-800 block">
                          Repeated talking episodes detected
                        </span>
                      )}
                    </div>
                    <span className="text-xs opacity-75 whitespace-nowrap">
                      {a.created_at ? new Date(a.created_at).toLocaleTimeString() : ""}
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-xs opacity-80">
                    <span>Status: {a.status}</span>
                    {a.session_id && (
                      <span className="text-slate-500 font-mono">
                        Session: {a.session_id.slice(0, 8)}...
                      </span>
                    )}
                  </div>
                  {a.status === "New" && (
                    <div className="flex gap-2 pt-1">
                      <button
                        onClick={() => handleAlertStatus(a.id, "Reviewed")}
                        className="text-xs px-2 py-1 bg-white border border-red-200 rounded hover:bg-red-50"
                      >
                        Review
                      </button>
                      <button
                        onClick={() => handleAlertStatus(a.id, "Dismissed")}
                        className="text-xs px-2 py-1 bg-white border border-red-200 rounded hover:bg-red-50"
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

        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
          <h2 className="text-xl font-semibold mb-4">Enroll Student (Webcam)</h2>
          <div className="space-y-3">
            <input
              className="w-full border border-slate-300 rounded-lg px-3 py-2"
              placeholder="Student name"
              value={enrollName}
              onChange={(e) => setEnrollName(e.target.value)}
              disabled={phase === "live"}
            />
            <input
              className="w-full border border-slate-300 rounded-lg px-3 py-2"
              placeholder="Roll number"
              value={enrollRoll}
              onChange={(e) => setEnrollRoll(e.target.value)}
              disabled={phase === "live"}
            />
            <div className="flex flex-wrap gap-2">
              {!cameraOn ? (
                <button
                  onClick={startCamera}
                  disabled={phase === "live"}
                  className="px-4 py-2 bg-slate-800 text-white rounded hover:bg-slate-900 disabled:opacity-50"
                >
                  Open Camera
                </button>
              ) : (
                <button
                  onClick={stopEnrollmentCamera}
                  className="px-4 py-2 border border-slate-300 rounded hover:bg-slate-50"
                >
                  Close Camera
                </button>
              )}
              <button
                onClick={captureAndEnroll}
                disabled={
                  !cameraOn || enrolling || !enrollName.trim() || !enrollRoll.trim() || phase === "live"
                }
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {enrolling ? "Enrolling…" : "Capture & Enroll"}
              </button>
            </div>
            {enrollMsg && <p className="text-sm text-slate-600">{enrollMsg}</p>}
            <div className="relative bg-slate-900 rounded-xl overflow-hidden aspect-video flex items-center justify-center">
              <video ref={videoRef} muted playsInline className="w-full h-full object-cover" />
              {!cameraOn && <span className="absolute text-slate-400 text-sm">Enrollment camera off</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
