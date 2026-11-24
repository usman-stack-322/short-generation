import { useCallback, useEffect, useRef, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { API_BASE, getHealth, listCelebrities, listProjects } from './api/client';
import ProtectedRoute from './components/ProtectedRoute';
import Sidebar from './components/Sidebar';
import { useAuth } from './context/AuthContext';
import CelebrityVaultPage from './pages/CelebrityVaultPage';
import CreateVideoPage from './pages/CreateVideoPage';
import DashboardPage from './pages/DashboardPage';
import LoginPage from './pages/LoginPage';
import RenderQueuePage from './pages/RenderQueuePage';

const ROUTE_TO_PAGE = {
  '/': 'dashboard',
  '/vault': 'vault',
  '/create': 'create',
  '/queue': 'queue',
};

const PAGE_TO_ROUTE = {
  dashboard: '/',
  vault: '/vault',
  create: '/create',
  queue: '/queue',
};

function StudioShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [health, setHealth] = useState(null);
  const [celebrities, setCelebrities] = useState([]);
  const [projects, setProjects] = useState([]);
  const [apiError, setApiError] = useState('');

  const initialLoadedRef = useRef(false);
  const refreshInFlightRef = useRef(null);
  const projectsInFlightRef = useRef(null);

  const activePage = ROUTE_TO_PAGE[location.pathname] || 'dashboard';

  const handleNavigate = useCallback(
    (pageId) => {
      navigate(PAGE_TO_ROUTE[pageId] || '/');
    },
    [navigate]
  );

  const handleLogout = useCallback(() => {
    logout();
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  const refreshAll = useCallback(async () => {
    if (refreshInFlightRef.current) {
      return refreshInFlightRef.current;
    }
    const promise = (async () => {
      try {
        const [h, celebs, projs] = await Promise.all([
          getHealth(),
          listCelebrities(),
          listProjects(),
        ]);
        setHealth(h);
        setCelebrities(celebs);
        setProjects(projs);
        setApiError('');
        return true;
      } catch (err) {
        setApiError(err.message || 'Unable to connect to Backend API.');
        return false;
      } finally {
        refreshInFlightRef.current = null;
      }
    })();
    refreshInFlightRef.current = promise;
    return promise;
  }, []);

  const refreshProjectsOnly = useCallback(async () => {
    if (projectsInFlightRef.current) {
      return projectsInFlightRef.current;
    }
    const promise = (async () => {
      try {
        const projs = await listProjects();
        setProjects(projs);
        setApiError('');
        return true;
      } catch (err) {
        setApiError(err.message || 'Unable to connect to Backend API.');
        return false;
      } finally {
        projectsInFlightRef.current = null;
      }
    })();
    projectsInFlightRef.current = promise;
    return promise;
  }, []);

  useEffect(() => {
    if (initialLoadedRef.current) return;
    initialLoadedRef.current = true;
    refreshAll();
  }, [refreshAll]);

  const activeJobCount = projects.filter(
    (p) => p.status === 'queued' || p.status === 'processing'
  ).length;

  return (
    <div className="min-h-screen bg-[#090B10] text-[#F8FAFC] lg:flex">
      <Sidebar
        activePage={activePage}
        onNavigate={handleNavigate}
        activeJobCount={activeJobCount}
        health={health}
        user={user}
        onLogout={handleLogout}
        mobileOpen={mobileOpen}
        onToggleMobile={() => setMobileOpen((prev) => !prev)}
      />

      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-8 lg:py-8">
        <div className="mx-auto max-w-6xl space-y-6">
          {apiError && (
            <div className="rounded-xl border border-[#F43F5E]/30 bg-[#F43F5E]/10 px-4 py-3 text-xs text-[#F43F5E]">
              Backend unreachable: {apiError} — confirm FastAPI is running at {API_BASE}.
            </div>
          )}

          <Routes>
            <Route
              path="/"
              element={
                <DashboardPage
                  celebrities={celebrities}
                  projects={projects}
                  health={health}
                  onNavigate={handleNavigate}
                  onRefresh={refreshAll}
                />
              }
            />
            <Route
              path="/vault"
              element={
                <CelebrityVaultPage celebrities={celebrities} onRefresh={refreshAll} />
              }
            />
            <Route
              path="/create"
              element={
                <CreateVideoPage
                  onCreated={async () => {
                    await refreshAll();
                    navigate('/queue');
                  }}
                />
              }
            />
            <Route
              path="/queue"
              element={
                <RenderQueuePage
                  projects={projects}
                  onRefresh={refreshAll}
                  onPollProjects={refreshProjectsOnly}
                  hasApiError={Boolean(apiError)}
                />
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <StudioShell />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
