import { useCallback, useEffect, useState } from 'react';
import { API_BASE, getHealth, listCelebrities, listProjects } from './api/client';
import Sidebar from './components/Sidebar';
import CelebrityVaultPage from './pages/CelebrityVaultPage';
import CreateVideoPage from './pages/CreateVideoPage';
import DashboardPage from './pages/DashboardPage';
import RenderQueuePage from './pages/RenderQueuePage';

export default function App() {
  const [activePage, setActivePage] = useState('dashboard');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [health, setHealth] = useState(null);
  const [celebrities, setCelebrities] = useState([]);
  const [projects, setProjects] = useState([]);
  const [apiError, setApiError] = useState('');

  const refreshAll = useCallback(async () => {
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
    } catch (err) {
      setApiError(err.message || 'Unable to connect to Backend API.');
    }
  }, []);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const activeJobCount = projects.filter(
    (p) => p.status === 'queued' || p.status === 'processing'
  ).length;

  return (
    <div className="min-h-screen bg-[#090B10] text-[#F8FAFC] lg:flex">
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
        activeJobCount={activeJobCount}
        health={health}
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

          {activePage === 'dashboard' && (
            <DashboardPage
              celebrities={celebrities}
              projects={projects}
              health={health}
              onNavigate={setActivePage}
              onRefresh={refreshAll}
            />
          )}

          {activePage === 'vault' && (
            <CelebrityVaultPage celebrities={celebrities} onRefresh={refreshAll} />
          )}

          {activePage === 'create' && (
            <CreateVideoPage
              onCreated={async () => {
                await refreshAll();
                setActivePage('queue');
              }}
            />
          )}

          {activePage === 'queue' && (
            <RenderQueuePage projects={projects} onRefresh={refreshAll} />
          )}
        </div>
      </main>
    </div>
  );
}
