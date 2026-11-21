import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Clock, Film, FolderSync, Plus, Search, Upload } from 'lucide-react';
import {
  createCelebrity,
  getLocalFolderScanStatus,
  startLocalFolderScan,
  uploadLocalClips,
} from '../api/client';
import ModalDialog from '../components/ModalDialog';

const CATEGORIES = ['All', 'NBA', 'Basketball', 'Celebrity'];

function formatDuration(totalSec) {
  const sec = Math.max(0, Math.round(totalSec || 0));
  const hrs = Math.floor(sec / 3600);
  const mins = Math.floor((sec % 3600) / 60);
  const rem = sec % 60;
  if (hrs > 0) return `${hrs}h ${mins}m`;
  if (mins > 0) return `${mins}m ${rem}s`;
  return `${rem}s`;
}

export default function CelebrityVaultPage({ celebrities, onRefresh }) {
  const [query, setQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('All');

  const [addOpen, setAddOpen] = useState(false);
  const [celebName, setCelebName] = useState('');
  const [celebCategory, setCelebCategory] = useState('NBA');
  const [celebAliases, setCelebAliases] = useState('');
  const [addError, setAddError] = useState('');
  const [adding, setAdding] = useState(false);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [targetCelebId, setTargetCelebId] = useState('');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploadTags, setUploadTags] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [uploadResult, setUploadResult] = useState('');
  const [uploading, setUploading] = useState(false);

  const [scanOpen, setScanOpen] = useState(false);
  const [scanFolder, setScanFolder] = useState('');
  const [scanCategory, setScanCategory] = useState('NBA');
  const [scanJob, setScanJob] = useState(null);
  const [scanError, setScanError] = useState('');
  const [startingScan, setStartingScan] = useState(false);

  useEffect(() => {
    if (!scanJob || scanJob.status !== 'running') return undefined;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getLocalFolderScanStatus(scanJob.scan_id);
        if (cancelled) return;
        setScanJob(latest);
        if (latest.status === 'completed') {
          await onRefresh();
        }
      } catch (err) {
        if (!cancelled) {
          setScanError(err.message);
        }
      }
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [scanJob?.scan_id, scanJob?.status, onRefresh]);

  async function handleStartFolderScan(e) {
    e.preventDefault();
    setScanError('');
    if (!scanFolder.trim()) {
      setScanError('Please enter your local Celebrity Vault folder path.');
      return;
    }
    setStartingScan(true);
    try {
      const started = await startLocalFolderScan({
        folderPath: scanFolder.trim(),
        category: scanCategory,
      });
      setScanJob(started);
    } catch (err) {
      setScanError(err.message);
    } finally {
      setStartingScan(false);
    }
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return celebrities.filter((c) => {
      const catOk = categoryFilter === 'All' || c.category.toLowerCase() === categoryFilter.toLowerCase();
      if (!catOk) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.category.toLowerCase().includes(q) ||
        (c.aliases || []).some((a) => a.toLowerCase().includes(q))
      );
    });
  }, [celebrities, query, categoryFilter]);

  function openUploadModal(preselectedId = '') {
    setTargetCelebId(preselectedId || (celebrities[0]?.id ?? ''));
    setSelectedFiles([]);
    setUploadTags('');
    setUploadError('');
    setUploadResult('');
    setUploadOpen(true);
  }

  async function handleAddCelebrity(e) {
    e.preventDefault();
    setAddError('');
    const aliases = celebAliases
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    setAdding(true);
    try {
      await createCelebrity({ name: celebName.trim(), category: celebCategory, aliases });
      setCelebName('');
      setCelebAliases('');
      setAddOpen(false);
      await onRefresh();
    } catch (err) {
      setAddError(err.message);
    } finally {
      setAdding(false);
    }
  }

  async function handleUploadClips(e) {
    e.preventDefault();
    setUploadError('');
    setUploadResult('');
    if (!targetCelebId) {
      setUploadError('Please select a celebrity first.');
      return;
    }
    if (selectedFiles.length === 0 || selectedFiles.length > 5) {
      setUploadError('Please select between 1 and 5 video files.');
      return;
    }
    setUploading(true);
    try {
      const res = await uploadLocalClips({
        celebrityId: targetCelebId,
        files: selectedFiles,
        tags: uploadTags,
      });
      setUploadResult(
        `Indexed ${res.uploaded} clip(s) into local vault` +
          (res.skipped_existing ? ` (${res.skipped_existing} duplicate skipped)` : '') +
          '.'
      );
      setSelectedFiles([]);
      setUploadTags('');
      await onRefresh();
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[#F8FAFC]">Celebrity Vault</h1>
          <p className="mt-1 text-sm text-[#94A3B8]">
            Manage NBA & celebrity talent profiles, aliases, and local disk video clips.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setScanError('');
              setScanOpen(true);
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-[#F59E0B] bg-[#F59E0B]/10 px-4 py-2 text-sm font-medium text-[#F59E0B] transition hover:bg-[#F59E0B]/20"
          >
            <FolderSync className="h-4 w-4" />
            Import Local Folder
          </button>
          <button
            type="button"
            onClick={() => {
              setAddError('');
              setAddOpen(true);
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-[#22283A] bg-[#131722] px-4 py-2 text-sm font-medium text-[#F8FAFC] transition hover:border-[#94A3B8]/50"
          >
            <Plus className="h-4 w-4 text-[#F59E0B]" />
            Add Celebrity
          </button>
          <button
            type="button"
            disabled={celebrities.length === 0}
            onClick={() => openUploadModal()}
            className="inline-flex items-center gap-2 rounded-lg bg-[#F59E0B] px-4 py-2 text-sm font-semibold text-[#090B10] transition hover:bg-[#D97706] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Upload className="h-4 w-4" />
            Upload Clip
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-[#22283A] bg-[#131722] p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#94A3B8]" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by celebrity name, alias (e.g. LBJ, Chef Curry), or category..."
            className="w-full rounded-lg border border-[#22283A] bg-[#090B10] py-2 pl-9 pr-3 text-sm text-[#F8FAFC] placeholder-[#94A3B8]/60 focus:border-[#F59E0B] focus:outline-none"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setCategoryFilter(cat)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                categoryFilter === cat
                  ? 'bg-[#F59E0B] text-[#090B10]'
                  : 'border border-[#22283A] bg-[#090B10] text-[#94A3B8] hover:text-[#F8FAFC]'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[#22283A] bg-[#131722]/60 p-12 text-center">
          <p className="text-sm font-medium text-[#F8FAFC]">No matching celebrities found</p>
          <p className="mt-1 text-xs text-[#94A3B8]">
            Click &ldquo;+ Add Celebrity&rdquo; or run bulk_sync_r2.py --local-only to index your local clips folder.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((celeb) => (
            <div
              key={celeb.id}
              className="flex flex-col justify-between rounded-xl border border-[#22283A] bg-[#131722] p-5"
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <h3 className="text-base font-semibold text-[#F8FAFC]">{celeb.name}</h3>
                  <span className="rounded-md border border-[#F59E0B]/30 bg-[#F59E0B]/10 px-2 py-0.5 text-xs font-medium text-[#F59E0B]">
                    {celeb.category}
                  </span>
                </div>

                {(celeb.aliases || []).length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {celeb.aliases.slice(0, 4).map((alias) => (
                      <span
                        key={alias}
                        className="rounded border border-[#22283A] bg-[#090B10] px-2 py-0.5 text-[11px] text-[#94A3B8]"
                      >
                        {alias}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="mt-5 flex items-center justify-between border-t border-[#22283A] pt-3">
                <div className="flex items-center gap-4 font-mono text-xs text-[#94A3B8]">
                  <span className="inline-flex items-center gap-1">
                    <Film className="h-3.5 w-3.5 text-[#F59E0B]" />
                    {celeb.clip_count} clips
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5 text-[#38BDF8]" />
                    {formatDuration(celeb.total_duration_sec)}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => openUploadModal(celeb.id)}
                  className="inline-flex items-center gap-1 rounded-lg border border-[#22283A] bg-[#090B10] px-2.5 py-1 text-xs font-medium text-[#F8FAFC] transition hover:border-[#F59E0B]"
                >
                  <Upload className="h-3 w-3 text-[#F59E0B]" />
                  Upload
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <ModalDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Add Celebrity"
        subtitle="Add aliases so auto-detection matches scripts and titles reliably."
      >
        <form onSubmit={handleAddCelebrity} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[#94A3B8]">Celebrity Name</label>
            <input
              type="text"
              required
              minLength={2}
              value={celebName}
              onChange={(e) => setCelebName(e.target.value)}
              placeholder="e.g. LeBron James"
              className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3 py-2 text-sm text-[#F8FAFC] focus:border-[#F59E0B] focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#94A3B8]">Category</label>
            <select
              value={celebCategory}
              onChange={(e) => setCelebCategory(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3 py-2 text-sm text-[#F8FAFC] focus:border-[#F59E0B] focus:outline-none"
            >
              <option value="NBA">NBA</option>
              <option value="Basketball">Basketball</option>
              <option value="Celebrity">Celebrity</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-[#94A3B8]">
              Aliases (comma-separated)
            </label>
            <input
              type="text"
              value={celebAliases}
              onChange={(e) => setCelebAliases(e.target.value)}
              placeholder="e.g. King James, LBJ, Bron"
              className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3 py-2 text-sm text-[#F8FAFC] focus:border-[#F59E0B] focus:outline-none"
            />
          </div>

          {addError && (
            <p className="rounded-lg border border-[#F43F5E]/30 bg-[#F43F5E]/10 px-3 py-2 text-xs text-[#F43F5E]">
              {addError}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setAddOpen(false)}
              className="rounded-lg border border-[#22283A] px-4 py-2 text-sm text-[#94A3B8] hover:text-[#F8FAFC]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={adding}
              className="rounded-lg bg-[#F59E0B] px-4 py-2 text-sm font-semibold text-[#090B10] hover:bg-[#D97706] disabled:opacity-60"
            >
              {adding ? 'Saving...' : 'Save Celebrity'}
            </button>
          </div>
        </form>
      </ModalDialog>

      <ModalDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        title="Upload Clip (Local Vault)"
        subtitle="Upload 1–5 MP4/MOV/MKV clips directly into generated/vault_uploads/ and index in Neon DB."
      >
        <form onSubmit={handleUploadClips} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[#94A3B8]">Celebrity</label>
            <select
              value={targetCelebId}
              onChange={(e) => setTargetCelebId(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3 py-2 text-sm text-[#F8FAFC] focus:border-[#F59E0B] focus:outline-none"
            >
              {celebrities.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.category})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-[#94A3B8]">
              Select 1–5 Video Clips
            </label>
            <input
              type="file"
              multiple
              accept=".mp4,.mov,.mkv,.webm,.m4v,video/*"
              onChange={(e) => setSelectedFiles(Array.from(e.target.files || []))}
              className="mt-1.5 block w-full rounded-lg border border-[#22283A] bg-[#090B10] p-2 text-xs text-[#94A3B8] file:mr-3 file:rounded-md file:border-0 file:bg-[#F59E0B] file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-[#090B10]"
            />
            {selectedFiles.length > 0 && (
              <p className="mt-1 font-mono text-xs text-[#94A3B8]">
                {selectedFiles.length} file(s) selected
              </p>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-[#94A3B8]">
              Scene Tags (optional, comma-separated)
            </label>
            <input
              type="text"
              value={uploadTags}
              onChange={(e) => setUploadTags(e.target.value)}
              placeholder="e.g. interview, espn, press_conference"
              className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3 py-2 text-sm text-[#F8FAFC] focus:border-[#F59E0B] focus:outline-none"
            />
          </div>

          {uploadError && (
            <p className="rounded-lg border border-[#F43F5E]/30 bg-[#F43F5E]/10 px-3 py-2 text-xs text-[#F43F5E]">
              {uploadError}
            </p>
          )}
          {uploadResult && (
            <p className="rounded-lg border border-[#10B981]/30 bg-[#10B981]/10 px-3 py-2 text-xs text-[#10B981]">
              {uploadResult}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setUploadOpen(false)}
              className="rounded-lg border border-[#22283A] px-4 py-2 text-sm text-[#94A3B8] hover:text-[#F8FAFC]"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={uploading}
              className="rounded-lg bg-[#F59E0B] px-4 py-2 text-sm font-semibold text-[#090B10] hover:bg-[#D97706] disabled:opacity-60"
            >
              {uploading ? 'Uploading & Probing...' : 'Upload & Index'}
            </button>
          </div>
        </form>
      </ModalDialog>

      <ModalDialog
        open={scanOpen}
        onClose={() => setScanOpen(false)}
        title="Import Local Folder"
        subtitle="Index your local <Celebrity Name>/**/* video library directly into Neon DB with zero file copying."
      >
        <form onSubmit={handleStartFolderScan} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[#94A3B8]">
              Root Folder Path
            </label>
            <input
              type="text"
              required
              disabled={scanJob?.status === 'running'}
              value={scanFolder}
              onChange={(e) => setScanFolder(e.target.value)}
              placeholder="D:\CelebrityClips"
              className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3 py-2 font-mono text-sm text-[#F8FAFC] placeholder-[#94A3B8]/60 focus:border-[#F59E0B] focus:outline-none disabled:opacity-60"
            />
            <p className="mt-1 text-[11px] text-[#94A3B8]">
              Tip: You can paste directly using Windows &ldquo;Copy as path&rdquo; (quotes are stripped automatically).
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-[#94A3B8]">Default Category</label>
            <select
              disabled={scanJob?.status === 'running'}
              value={scanCategory}
              onChange={(e) => setScanCategory(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3 py-2 text-sm text-[#F8FAFC] focus:border-[#F59E0B] focus:outline-none disabled:opacity-60"
            >
              <option value="NBA">NBA</option>
              <option value="Basketball">Basketball</option>
              <option value="Celebrity">Celebrity</option>
            </select>
          </div>

          {scanJob && (
            <div className="space-y-3 rounded-lg border border-[#22283A] bg-[#090B10] p-4">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-[#F8FAFC]">
                  {scanJob.status === 'running'
                    ? `Scanning${scanJob.current_celebrity ? `: ${scanJob.current_celebrity}` : '...'}`
                    : scanJob.status === 'completed'
                    ? 'Bulk Index Completed'
                    : 'Scan Failed'}
                </span>
                <span
                  className={`font-mono font-medium ${
                    scanJob.status === 'completed'
                      ? 'text-[#10B981]'
                      : scanJob.status === 'failed'
                      ? 'text-[#F43F5E]'
                      : 'text-[#38BDF8]'
                  }`}
                >
                  {scanJob.total_files_found > 0
                    ? `${Math.round((scanJob.processed_files / scanJob.total_files_found) * 100)}%`
                    : scanJob.status === 'completed'
                    ? '100%'
                    : '0%'}
                </span>
              </div>

              <div className="h-2 w-full overflow-hidden rounded-full bg-[#131722]">
                <div
                  className={`h-full transition-all duration-300 ${
                    scanJob.status === 'completed'
                      ? 'bg-[#10B981]'
                      : scanJob.status === 'failed'
                      ? 'bg-[#F43F5E]'
                      : 'bg-[#38BDF8]'
                  }`}
                  style={{
                    width: `${
                      scanJob.total_files_found > 0
                        ? Math.round((scanJob.processed_files / scanJob.total_files_found) * 100)
                        : scanJob.status === 'completed'
                        ? 100
                        : 10
                    }%`,
                  }}
                />
              </div>

              <div className="grid grid-cols-2 gap-2 font-mono text-xs sm:grid-cols-4">
                <div className="rounded border border-[#22283A] bg-[#131722] p-2">
                  <p className="text-[10px] text-[#94A3B8]">Files Scanned</p>
                  <p className="mt-0.5 text-[#F8FAFC]">
                    {scanJob.processed_files}/{scanJob.total_files_found}
                  </p>
                </div>
                <div className="rounded border border-[#22283A] bg-[#131722] p-2">
                  <p className="text-[10px] text-[#94A3B8]">Clips Added</p>
                  <p className="mt-0.5 text-[#10B981]">{scanJob.inserted}</p>
                </div>
                <div className="rounded border border-[#22283A] bg-[#131722] p-2">
                  <p className="text-[10px] text-[#94A3B8]">Celebrities</p>
                  <p className="mt-0.5 text-[#F59E0B]">{scanJob.celebrities_created}</p>
                </div>
                <div className="rounded border border-[#22283A] bg-[#131722] p-2">
                  <p className="text-[10px] text-[#94A3B8]">Skipped</p>
                  <p className="mt-0.5 text-[#94A3B8]">{scanJob.skipped_existing}</p>
                </div>
              </div>
            </div>
          )}

          {(scanError || scanJob?.error_message) && (
            <div className="flex items-start gap-2 rounded-lg border border-[#F43F5E]/30 bg-[#F43F5E]/10 px-3 py-2 text-xs text-[#F43F5E]">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{scanError || scanJob.error_message}</span>
            </div>
          )}

          {scanJob?.status === 'completed' && !scanError && (
            <div className="flex items-center gap-2 rounded-lg border border-[#10B981]/30 bg-[#10B981]/10 px-3 py-2 text-xs text-[#10B981]">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>
                Indexed {scanJob.inserted} new clip(s) across {scanJob.celebrities_created} new celebrity folder(s).
              </span>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setScanOpen(false)}
              className="rounded-lg border border-[#22283A] px-4 py-2 text-sm text-[#94A3B8] hover:text-[#F8FAFC]"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={startingScan || scanJob?.status === 'running'}
              className="rounded-lg bg-[#F59E0B] px-4 py-2 text-sm font-semibold text-[#090B10] hover:bg-[#D97706] disabled:opacity-60"
            >
              {scanJob?.status === 'running'
                ? 'Scanning Vault...'
                : startingScan
                ? 'Starting...'
                : 'Start Bulk Index'}
            </button>
          </div>
        </form>
      </ModalDialog>
    </div>
  );
}
