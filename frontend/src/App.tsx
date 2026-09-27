import TeacherDashboard from "./components/TeacherDashboard";
import TeacherLogin from "./components/TeacherLogin";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import "./App.css";

function AppShell() {
  const { user, loading, signOut } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-600">
        Restoring session…
      </div>
    );
  }

  if (!user) {
    return <TeacherLogin />;
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-800 truncate">
              Signed in as {user.email}
            </p>
          </div>
          <button
            type="button"
            onClick={() => signOut()}
            className="shrink-0 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            Log out
          </button>
        </div>
      </header>
      <TeacherDashboard />
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

export default App;
