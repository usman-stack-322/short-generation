import { useState } from 'react';
import { Download, Film, FolderOpen, HardDrive, Play, PlusCircle, Trash2, Users, Video } from 'lucide-react';
import { deleteProject, getProjectVideoUrl } from '../api/client';
import ModalDialog from '../components/ModalDialog';
import StatusBadge from '../components/StatusBadge';

export default function DashboardPage({ celebrities, projects, health, onNavigate, onRefresh }) {
  const [previewProject, setPreviewProject] = useState(null);
  const [projectToDelete, setProjectToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  async function handleConfirmDelete() {
    if (!projectToDelete) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteProject(projectToDelete.id);
      if (previewProject?.id === projectToDelete.id) {
        setPreviewProject(null);
      }
      setProjectToDelete(null);
      if (onRefresh) await onRefresh();
    } catch (err) {
      setDeleteError(err.message || 'Failed to delete project.');
    } finally {
      setDeleting(false);
    }
  }

  const totalClips = celebrities.reduce((acc, c) => acc + (c.clip_count || 0), 0);
  const totalSec = celebrities.reduce((acc, c) => acc + (c.total_duration_sec || 0), 0);
  const totalHours = (totalSec / 3600).toFixed(2);
  const completedCount = projects.filter((p) => p.status === 'completed').length;
  const activeCount = projects.filter((p) => p.status === 'queued' || p.status === 'processing').length;
  const storageText = health?.storage_mode === 'r2' ? 'R2 Cloud' : 'Local Vault';

  const kpis = [
    {
      label: 'Total Celebrities',
      value: celebrities.length,
      sub: 'Indexed talent profiles',
      icon: Users,
    },
    {
      label: 'Total Vault Clips & Hours',
      value: `${totalClips}`,
      sub: `${totalHours} hrs ready footage`,
      icon: Film,
    },
    {
      label: 'Rendered Videos',
      value: `${completedCount}`,
      sub: activeCount > 0 ? `${activeCount} active in queue` : `${projects.length} total projects`,
      icon: Video,
    },
    {
      label: 'Storage Mode',
      value: storageText,
      sub: health?.storage_mode === 'r2' ? 'Zero-egress R2 bucket' : '100% Free Local Disk + Neon',
      icon: HardDrive,
    },
  ];

  const recentProjects = projects.slice(0, 6);

  return (
    <div className="space-y-8">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[#F8FAFC]">Studio Dashboard</h1>
          <p className="mt-1 text-sm text-[#94A3B8]">
            Monitor your celebrity footage vault and launch 9:16 NBA Shorts on your local PC worker.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => onNavigate('vault')}
            className="inline-flex items-center gap-2 rounded-lg border border-[#22283A] bg-[#131722] px-4 py-2 text-sm font-medium text-[#F8FAFC] transition hover:border-[#94A3B8]/50"
          >
            <FolderOpen className="h-4 w-4 text-[#94A3B8]" />
            Celebrity Vault
          </button>
          <button
            type="button"
            onClick={() => onNavigate('create')}
            className="inline-flex items-center gap-2 rounded-lg bg-[#F59E0B] px-4 py-2 text-sm font-semibold text-[#090B10] transition hover:bg-[#D97706]"
          >
            <PlusCircle className="h-4 w-4" />
            Create New Video
          </button>
        </div>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div
              key={kpi.label}
              className="rounded-xl border border-[#22283A] bg-[#131722] p-5"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wider text-[#94A3B8]">
                  {kpi.label}
                </span>
                <Icon className="h-4 w-4 text-[#F59E0B]" />
              </div>
              <p className="mt-3 font-mono text-2xl font-semibold text-[#F8FAFC]">{kpi.value}</p>
              <p className="mt-1 text-xs text-[#94A3B8]">{kpi.sub}</p>
            </div>
          );
        })}
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-[#F8FAFC]">Recent Renders</h2>
          <button
            type="button"
            onClick={() => onNavigate('queue')}
            className="text-xs font-medium text-[#F59E0B] hover:text-[#D97706]"
          >
            Open Render Queue →
          </button>
        </div>

        {recentProjects.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[#22283A] bg-[#131722]/60 p-10 text-center">
            <p className="text-sm font-medium text-[#F8FAFC]">No renders queued yet</p>
            <p className="mt-1 text-xs text-[#94A3B8]">
              Add a celebrity clip or generate your first Short script in Create Video.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {recentProjects.map((project) => {
              const videoUrl = getProjectVideoUrl(project.id);
              const isCompleted = project.status === 'completed' && project.output_r2_key;
              return (
                <div
                  key={project.id}
                  className="flex flex-col justify-between rounded-xl border border-[#22283A] bg-[#131722] p-5"
                >
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <span className="rounded border border-[#22283A] bg-[#090B10] px-2 py-0.5 font-mono text-[11px] text-[#94A3B8]">
                        {project.mode === 'long' ? '16:9 Long' : '9:16 Short'}
                      </span>
                      <StatusBadge status={project.status} />
                    </div>
                    <h3 className="mt-3 line-clamp-2 text-sm font-semibold text-[#F8FAFC]">
                      {project.title}
                    </h3>
                    <p className="mt-1 text-xs text-[#94A3B8]">
                      Voice: <span className="font-mono">{project.voice_name}</span>
                    </p>
                  </div>

                  <div className="mt-4 flex items-center justify-between gap-2 border-t border-[#22283A] pt-3">
                    <span className="font-mono text-xs text-[#94A3B8]">
                      {project.latest_job?.progress_pct ?? 0}% • {project.latest_job?.current_step || 'queued'}
                    </span>

                    <div className="flex items-center gap-1.5">
                      {isCompleted ? (
                        <>
                          <button
                            type="button"
                            onClick={() => setPreviewProject(project)}
                            className="inline-flex items-center gap-1 rounded-lg border border-[#22283A] bg-[#090B10] px-2.5 py-1 text-xs font-medium text-[#F8FAFC] hover:border-[#F59E0B]"
                          >
                            <Play className="h-3 w-3 text-[#F59E0B]" />
                            Preview
                          </button>
                          <a
                            href={videoUrl}
                            download={`${project.id}.mp4`}
                            className="inline-flex items-center gap-1 rounded-lg bg-[#F59E0B] px-2.5 py-1 text-xs font-semibold text-[#090B10] hover:bg-[#D97706]"
                          >
                            <Download className="h-3 w-3" />
                            MP4
                          </a>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onNavigate('queue')}
                          className="px-1 text-xs font-medium text-[#38BDF8] hover:underline"
                        >
                          Track
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={() => {
                          setDeleteError('');
                          setProjectToDelete(project);
                        }}
                        aria-label={`Delete ${project.title}`}
                        title="Delete project & rendered MP4"
                        className="inline-flex items-center rounded-lg border border-[#22283A] bg-[#090B10] p-1.5 text-[#94A3B8] transition hover:border-[#F43F5E]/50 hover:bg-[#F43F5E]/10 hover:text-[#F43F5E]"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <ModalDialog
        open={Boolean(projectToDelete)}
        onClose={() => !deleting && setProjectToDelete(null)}
        title="Delete Project?"
        subtitle="Removes the project record and any local rendered MP4 from disk."
      >
        {projectToDelete && (
          <div className="space-y-4">
            <p className="text-sm text-[#F8FAFC]">
              Delete <span className="font-semibold">&ldquo;{projectToDelete.title}&rdquo;</span>? This cannot be undone.
            </p>
            {deleteError && (
              <p className="rounded-lg border border-[#F43F5E]/30 bg-[#F43F5E]/10 px-3 py-2 text-xs text-[#F43F5E]">
                {deleteError}
              </p>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={deleting}
                onClick={() => setProjectToDelete(null)}
                className="rounded-lg border border-[#22283A] px-4 py-2 text-sm text-[#94A3B8] hover:text-[#F8FAFC] disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={handleConfirmDelete}
                className="rounded-lg bg-[#F43F5E] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#E11D48] disabled:opacity-60"
              >
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        )}
      </ModalDialog>

      <ModalDialog
        open={Boolean(previewProject)}
        onClose={() => setPreviewProject(null)}
        title={previewProject?.title || 'Render Preview'}
        subtitle={previewProject ? `${previewProject.mode === 'long' ? '16:9 Long' : '9:16 Short'} • H.264 MP4` : ''}
      >
        {previewProject && (
          <div className="space-y-4">
            <div className="flex justify-center rounded-lg border border-[#22283A] bg-[#090B10] p-2">
              <video
                controls
                autoPlay
                src={getProjectVideoUrl(previewProject.id)}
                className={
                  previewProject.mode === 'long'
                    ? 'max-h-[360px] w-full rounded'
                    : 'max-h-[460px] w-auto rounded'
                }
              />
            </div>
            <div className="flex justify-end">
              <a
                href={getProjectVideoUrl(previewProject.id)}
                download={`${previewProject.id}.mp4`}
                className="inline-flex items-center gap-2 rounded-lg bg-[#F59E0B] px-4 py-2 text-sm font-semibold text-[#090B10] hover:bg-[#D97706]"
              >
                <Download className="h-4 w-4" />
                Download MP4
              </a>
            </div>
          </div>
        )}
      </ModalDialog>
    </div>
  );
}
