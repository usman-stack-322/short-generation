import { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Download, RefreshCw, Trash2 } from 'lucide-react';
import { deleteProject, getProjectVideoUrl } from '../api/client';
import ModalDialog from '../components/ModalDialog';
import StatusBadge from '../components/StatusBadge';

const PIPELINE_STEPS = ['script', 'audio', 'clips', 'captions', 'render'];

export default function RenderQueuePage({ projects, onRefresh }) {
  const [refreshing, setRefreshing] = useState(false);
  const [projectToDelete, setProjectToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  async function handleConfirmDelete() {
    if (!projectToDelete) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteProject(projectToDelete.id);
      setProjectToDelete(null);
      await onRefresh();
    } catch (err) {
      setDeleteError(err.message || 'Failed to delete project.');
    } finally {
      setDeleting(false);
    }
  }

  const hasActiveJobs = projects.some(
    (p) => p.status === 'queued' || p.status === 'processing'
  );

  useEffect(() => {
    if (!hasActiveJobs) return undefined;
    const timer = window.setInterval(() => {
      onRefresh();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [hasActiveJobs, onRefresh]);

  async function handleManualRefresh() {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[#F8FAFC]">
            Render Queue & Library
          </h1>
          <p className="mt-1 text-sm text-[#94A3B8]">
            Track live worker progress (script → audio → clips → captions → render) and download finished MP4s.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {hasActiveJobs && (
            <span className="inline-flex items-center gap-2 rounded-full border border-[#38BDF8]/30 bg-[#38BDF8]/10 px-3 py-1 text-xs font-medium text-[#38BDF8]">
              <span className="h-2 w-2 animate-pulse rounded-full bg-[#38BDF8]" />
              Polling every 2.5s
            </span>
          )}
          <button
            type="button"
            onClick={handleManualRefresh}
            className="inline-flex items-center gap-2 rounded-lg border border-[#22283A] bg-[#131722] px-3.5 py-2 text-xs font-medium text-[#F8FAFC] hover:border-[#F59E0B]"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {projects.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[#22283A] bg-[#131722]/60 p-12 text-center">
          <p className="text-sm font-medium text-[#F8FAFC]">Your Render Queue is empty</p>
          <p className="mt-1 text-xs text-[#94A3B8]">
            Submit a title or script in Create Video, and keep run_worker.py running to render locally.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {projects.map((project) => {
            const job = project.latest_job;
            const currentStep = (job?.current_step || project.status || 'queued').toLowerCase();
            const progressPct = job?.progress_pct ?? 0;
            const currentStepIndex = PIPELINE_STEPS.indexOf(currentStep);
            const isCompleted = project.status === 'completed' && project.output_r2_key;
            const isFailed = project.status === 'failed' || job?.status === 'failed';
            const videoUrl = getProjectVideoUrl(project.id);

            return (
              <div
                key={project.id}
                className="rounded-xl border border-[#22283A] bg-[#131722] p-5"
              >
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={project.status} />
                      <span className="rounded border border-[#22283A] bg-[#090B10] px-2 py-0.5 font-mono text-[11px] text-[#94A3B8]">
                        {project.mode === 'long' ? '16:9 Long' : '9:16 Short'}
                      </span>
                      <span className="font-mono text-xs text-[#94A3B8]">
                        {project.voice_name}
                      </span>
                    </div>
                    <h2 className="mt-2 text-base font-semibold text-[#F8FAFC]">{project.title}</h2>
                    {project.detected_celebrities?.length > 0 && (
                      <p className="mt-1 text-xs text-[#94A3B8]">
                        Detected:{' '}
                        <span className="text-[#F59E0B]">
                          {project.detected_celebrities.join(', ')}
                        </span>
                      </p>
                    )}
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    {isCompleted && (
                      <a
                        href={videoUrl}
                        download={`${project.id}.mp4`}
                        className="inline-flex items-center gap-2 rounded-lg bg-[#F59E0B] px-4 py-2 text-xs font-semibold text-[#090B10] hover:bg-[#D97706]"
                      >
                        <Download className="h-3.5 w-3.5" />
                        Download MP4
                      </a>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setDeleteError('');
                        setProjectToDelete(project);
                      }}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[#22283A] bg-[#090B10] px-3 py-2 text-xs font-medium text-[#94A3B8] transition hover:border-[#F43F5E]/50 hover:bg-[#F43F5E]/10 hover:text-[#F43F5E]"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Delete
                    </button>
                  </div>
                </div>

                <div className="mt-4 space-y-2.5">
                  <div className="flex items-center justify-between font-mono text-xs">
                    <span className="text-[#94A3B8]">
                      Step: <span className="text-[#F8FAFC]">{currentStep}</span>
                      {job?.worker_id ? ` • Worker: ${job.worker_id}` : ''}
                    </span>
                    <span className="text-[#F8FAFC]">{progressPct}%</span>
                  </div>

                  <div className="h-2 w-full overflow-hidden rounded-full bg-[#090B10]">
                    <div
                      className={`h-full transition-all duration-300 ${
                        isFailed
                          ? 'bg-[#F43F5E]'
                          : isCompleted
                          ? 'bg-[#10B981]'
                          : 'bg-[#38BDF8]'
                      }`}
                      style={{ width: `${isCompleted ? 100 : progressPct}%` }}
                    />
                  </div>

                  <div className="flex flex-wrap gap-2 pt-1">
                    {PIPELINE_STEPS.map((step, idx) => {
                      const done = isCompleted || currentStepIndex > idx;
                      const active = !isCompleted && !isFailed && currentStepIndex === idx;
                      return (
                        <span
                          key={step}
                          className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-mono text-[11px] ${
                            done
                              ? 'border-[#10B981]/30 bg-[#10B981]/10 text-[#10B981]'
                              : active
                              ? 'border-[#38BDF8]/40 bg-[#38BDF8]/10 text-[#38BDF8]'
                              : 'border-[#22283A] bg-[#090B10] text-[#94A3B8]'
                          }`}
                        >
                          {done && <CheckCircle2 className="h-3 w-3" />}
                          {step}
                        </span>
                      );
                    })}
                  </div>
                </div>

                {isFailed && job?.error_message && (
                  <div className="mt-4 flex items-start gap-2 rounded-lg border border-[#F43F5E]/30 bg-[#F43F5E]/10 p-3 text-xs text-[#F43F5E]">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span className="break-words font-mono">{job.error_message}</span>
                  </div>
                )}

                {isCompleted && (
                  <div className="mt-5 grid gap-4 border-t border-[#22283A] pt-4 lg:grid-cols-2">
                    <div className="flex justify-center rounded-lg border border-[#22283A] bg-[#090B10] p-2">
                      <video
                        controls
                        preload="metadata"
                        src={videoUrl}
                        className={
                          project.mode === 'long'
                            ? 'max-h-[280px] w-full rounded'
                            : 'max-h-[360px] w-auto rounded'
                        }
                      />
                    </div>
                    <div className="flex flex-col justify-between rounded-lg border border-[#22283A] bg-[#090B10] p-4">
                      <div>
                        <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8]">
                          Narration Script
                        </p>
                        <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-[#F8FAFC]">
                          {project.final_script || project.raw_input}
                        </p>
                      </div>
                      <p className="mt-3 truncate font-mono text-[11px] text-[#94A3B8]">
                        Output: {project.output_r2_key}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <ModalDialog
        open={Boolean(projectToDelete)}
        onClose={() => !deleting && setProjectToDelete(null)}
        title="Delete Project?"
        subtitle="Removes the project record, render job history, and any local rendered MP4."
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
    </div>
  );
}
