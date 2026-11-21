import { Clapperboard, Film, FolderOpen, LayoutDashboard, Menu, PlusCircle, Server, X } from 'lucide-react';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Studio Dashboard', icon: LayoutDashboard },
  { id: 'vault', label: 'Celebrity Vault', icon: FolderOpen },
  { id: 'create', label: 'Create Video', icon: PlusCircle },
  { id: 'queue', label: 'Render Queue & Library', icon: Film },
];

export default function Sidebar({
  activePage,
  onNavigate,
  activeJobCount,
  health,
  mobileOpen,
  onToggleMobile,
}) {
  const storageLabel =
    health?.storage_mode === 'r2' ? 'Cloudflare R2' : 'Local Vault (Free)';

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-[#090B10]/80 lg:hidden"
          onClick={onToggleMobile}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-[#22283A] bg-[#0D1017] transition-transform duration-200 lg:static lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between border-b border-[#22283A] px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#F59E0B] text-[#090B10]">
              <Clapperboard className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-semibold tracking-tight text-[#F8FAFC]">
                AI Shorts Studio
              </p>
              <p className="font-mono text-[11px] text-[#94A3B8]">v2 • Hybrid Phase 2</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onToggleMobile}
            className="rounded-lg p-1 text-[#94A3B8] hover:text-[#F8FAFC] lg:hidden"
            aria-label="Close navigation"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 p-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activePage === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  onNavigate(item.id);
                  if (mobileOpen) onToggleMobile();
                }}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm font-medium transition ${
                  isActive
                    ? 'bg-[#131722] text-[#F8FAFC] ring-1 ring-[#F59E0B]/50'
                    : 'text-[#94A3B8] hover:bg-[#131722]/70 hover:text-[#F8FAFC]'
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <Icon
                    className={`h-4 w-4 ${isActive ? 'text-[#F59E0B]' : 'text-[#94A3B8]'}`}
                  />
                  {item.label}
                </span>
                {item.id === 'queue' && activeJobCount > 0 && (
                  <span className="rounded-full bg-[#38BDF8]/15 px-2 py-0.5 font-mono text-xs text-[#38BDF8]">
                    {activeJobCount}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="border-t border-[#22283A] p-4">
          <div className="rounded-lg border border-[#22283A] bg-[#131722] p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 text-[#94A3B8]">
                <Server className="h-3.5 w-3.5 text-[#F59E0B]" />
                Backend API
              </span>
              <span
                className={`font-medium ${
                  health?.status === 'ok' ? 'text-[#10B981]' : 'text-[#F43F5E]'
                }`}
              >
                {health?.status === 'ok' ? 'Online' : 'Offline'}
              </span>
            </div>
            <p className="mt-1.5 font-mono text-[11px] text-[#94A3B8]">
              Storage: <span className="text-[#F8FAFC]">{storageLabel}</span>
            </p>
          </div>
        </div>
      </aside>

      <header className="flex items-center justify-between border-b border-[#22283A] bg-[#0D1017] px-4 py-3 lg:hidden">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#F59E0B] text-[#090B10]">
            <Clapperboard className="h-4 w-4" />
          </div>
          <span className="text-sm font-semibold text-[#F8FAFC]">AI Shorts Studio v2</span>
        </div>
        <button
          type="button"
          onClick={onToggleMobile}
          className="rounded-lg border border-[#22283A] bg-[#131722] p-2 text-[#F8FAFC]"
          aria-label="Open menu"
        >
          <Menu className="h-4 w-4" />
        </button>
      </header>
    </>
  );
}
