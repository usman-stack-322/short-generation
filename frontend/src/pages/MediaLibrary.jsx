import MediaFileInput from "../components/MediaFileInput";
import { useEffect, useState } from "react";
import { FolderOpen, Lock, Upload } from "lucide-react";
import { api, mediaUrl } from "../services/api";
import { PageHeader, EmptyState } from "../components/Shell";
import { Button, Notice, Loading } from "../components/UI";

export default function MediaLibrary() {
  const role = localStorage.getItem("role") || "MEMBER";
  const isAdmin = ["OWNER", "ADMIN"].includes(role);
  const writable = isAdmin;

  const [collections, setCollections] = useState([]);
  const [people, setPeople] = useState([]);
  const [selected, setSelected] = useState("");
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [approvalFilter, setApprovalFilter] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [initializing, setInitializing] = useState(true);

  const visibleRows = (rows || []).filter(
    (r) =>
      `${r.name} ${(r.tags || []).join(" ")}`.toLowerCase().includes(query.toLowerCase()) &&
      (!typeFilter || r.media_type === typeFilter) &&
      (!approvalFilter || (approvalFilter === "approved") === r.approved)
  );

  useEffect(() => {
    let live = true;
    Promise.all([
      api("/library/collections"),
      isAdmin ? api("/personalities").catch(() => []) : Promise.resolve([]),
    ])
      .then(([c, p]) => {
        if (!live) return;
        setCollections(c || []);
        setPeople(p || []);
        setSelected((c && c[0]?.id) || "");
      })
      .catch((e) => live && setError(e.message))
      .finally(() => live && setInitializing(false));
    return () => {
      live = false;
    };
  }, [refresh, isAdmin]);

  useEffect(() => {
    let live = true;
    setRows(null);
    if (!selected) {
      setRows([]);
      return;
    }
    api(`/library/collections/${selected}/media`)
      .then((data) => {
        if (live) {
          setRows(data || []);
          setError("");
        }
      })
      .catch((e) => {
        if (live) {
          setError(e.message);
          setRows([]);
        }
      });
    return () => {
      live = false;
    };
  }, [selected, refresh]);

  async function reload() {
    if (!selected) return;
    setRows(await api(`/library/collections/${selected}/media`));
  }

  async function act(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function create(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    act(async () => {
      const row = await api("/library/collections", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          channel_id: null,
        }),
      });
      setCollections((c) => [...c, row]);
      setSelected(row.id);
    });
  }

  function upload(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (!form.get("personality_id")) form.delete("personality_id");
    act(async () => {
      await api(`/library/collections/${selected}/media`, { method: "POST", body: form });
      await reload();
    });
  }

  return (
    <div className="media-library">
      <PageHeader
        title="Media Library"
        eyebrow="REUSABLE STUDIO MEDIA"
        description="Approved source media collections for Hybrid Shorts. Collection audio is separate from generated narration."
        action={
          !isAdmin && (
            <span className="studio-lock-pill">
              <Lock size={12} />
              <span>Library Uploads Locked to Owner/Admin</span>
            </span>
          )
        }
      />

      {error && <Notice>{error}</Notice>}
      {error && (
        <Button
          variant="secondary"
          onClick={() => {
            setError("");
            setRefresh((n) => n + 1);
          }}
        >
          Retry loading library
        </Button>
      )}
      {initializing && <Loading />}
      {message && <Notice type="success">{message}</Notice>}

      <div className="studio-grid-2" style={{ marginBottom: 18 }}>
        <section className="studio-card">
          <div className="studio-card-head">
            <h2>
              <FolderOpen size={17} />
              <span>Select Collection</span>
            </h2>
            {!writable && (
              <span className="studio-lock-pill">
                <Lock size={12} />
                <span>View Only</span>
              </span>
            )}
          </div>
          <div className="studio-field">
            <label className="studio-label" htmlFor="lib-select">Collection</label>
            <select id="lib-select" value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">Choose collection</option>
              {collections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        </section>

        <section className="studio-card">
          <div className="studio-card-head">
            <h2>
              <Upload size={17} />
              <span>Create Collection</span>
            </h2>
            {!writable && (
              <span className="studio-lock-pill">
                <Lock size={12} />
                <span>Owner Only</span>
              </span>
            )}
          </div>
          <form className="form-stack" onSubmit={create}>
            <label>
              Collection Name
              <input name="name" minLength={2} maxLength={160} required disabled={!writable} />
            </label>
            <Button disabled={busy || !writable}>
              {!writable && <Lock size={14} />}
              <span>{writable ? "Create Collection" : "Locked (Owner/Admin Only)"}</span>
            </Button>
          </form>
        </section>
      </div>

      {selected && writable && <FolderImport selected={selected} reload={reload} onError={setError} />}

      {selected && writable && (
        <section className="studio-card" style={{ marginBottom: 18 }}>
          <h3>Upload Rights-Cleared Asset</h3>
          <form className="form-stack" onSubmit={upload}>
            <div className="form-row">
              <label>
                Name
                <input name="name" required maxLength={160} />
              </label>
              <label>
                Media Type
                <select name="media_type" defaultValue="photo">
                  <option value="photo">Photo</option>
                  <option value="clip">Video clip</option>
                  <option value="audio">Audio</option>
                  <option value="brand">Brand / overlay</option>
                </select>
              </label>
            </div>
            <div className="form-row">
              <label>
                Creator
                <input name="creator" required maxLength={200} defaultValue="Workspace asset" />
              </label>
              <label>
                License
                <select name="license" defaultValue="Own work">
                  <option value="Own work">Own work</option>
                  <option value="Written permission">Written permission</option>
                  <option value="CC0">CC0</option>
                  <option value="CC BY 4.0">CC BY 4.0</option>
                </select>
              </label>
            </div>
            {people.length > 0 && (
              <label>
                Personality (optional)
                <select name="personality_id" defaultValue="">
                  <option value="">None</option>
                  {people.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              Source URL (for CC licenses)
              <input name="source_url" maxLength={1000} />
            </label>
            <label>
              Credit note
              <input name="credit" maxLength={2000} />
            </label>
            <MediaFileInput name="file" required />
            <label className="checkbox-label">
              <input type="checkbox" name="rights_confirmed" value="true" required />
              I confirm permission to reuse and modify this asset
            </label>
            <label className="checkbox-label">
              <input type="checkbox" name="identity_confirmed" value="true" />
              Identity confirmed (if tied to a personality)
            </label>
            <Button disabled={busy}>Upload Media</Button>
          </form>
        </section>
      )}

      <section className="studio-card">
        <div className="studio-card-head">
          <h2>Media Assets ({visibleRows.length})</h2>
        </div>
        <div className="form-row" style={{ marginBottom: 14 }}>
          <label>
            Search names or tags
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search..." />
          </label>
          <label>
            Media Type
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
              <option value="">All types</option>
              <option value="photo">Photos</option>
              <option value="clip">Video clips</option>
              <option value="audio">Audio</option>
              <option value="brand">Brand</option>
            </select>
          </label>
          <label>
            Approval
            <select value={approvalFilter} onChange={(e) => setApprovalFilter(e.target.value)}>
              <option value="">All</option>
              <option value="approved">Approved</option>
              <option value="pending">Needs review</option>
            </select>
          </label>
        </div>

        {rows === null ? (
          <Loading />
        ) : !visibleRows.length ? (
          <EmptyState
            title={rows.length ? "No matching media" : "No saved media in selected collection"}
            detail={
              rows.length
                ? "Clear search or change filters."
                : "Use the Celebrity Folder tab for instant bulk celebrity video/photo vaults, or create a collection above."
            }
          />
        ) : (
          <div className="library-grid">
            {visibleRows.map((row) => (
              <article key={row.id} className="scene-photo">
                <h3>{row.name}</h3>
                {row.media_type === "audio" ? (
                  <audio controls crossOrigin="use-credentials" src={mediaUrl(row.preview_url)} />
                ) : row.media_type === "clip" ? (
                  <video controls crossOrigin="use-credentials" src={mediaUrl(row.preview_url)} />
                ) : (
                  <img crossOrigin="use-credentials" src={mediaUrl(row.preview_url)} alt={row.name} />
                )}
                <p>
                  {row.media_type} / {row.approved ? "Approved" : "Needs review"} / Used {row.usage_count} times
                </p>
                <p>
                  {row.creator} / {row.license}
                </p>
                {row.source_url && (
                  <a href={row.source_url} target="_blank" rel="noreferrer">
                    Source
                  </a>
                )}
                <p>{row.credit}</p>
                {!row.available && <Notice>File missing. Upload a replacement.</Notice>}
                {row.media_type === "audio" && row.approved && role === "OWNER" && (
                  <Button
                    variant="secondary"
                    onClick={() =>
                      act(async () => {
                        const r = await api(`/library/media/${row.id}/workspace-music`, {
                          method: "POST",
                        });
                        setMessage(r.detail);
                      })
                    }
                  >
                    Share as workspace background music
                  </Button>
                )}
                {writable && (
                  <>
                    <form
                      className="form-stack"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const f = new FormData(event.currentTarget);
                        act(async () => {
                          await api(`/library/media/${row.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({
                              name: f.get("name"),
                              tags: String(f.get("tags") || "")
                                .split(",")
                                .map((t) => t.trim())
                                .filter(Boolean),
                              credit: f.get("credit"),
                              description: f.get("description"),
                              approved: f.get("approved") === "on",
                            }),
                          });
                          await reload();
                        });
                      }}
                    >
                      <label>
                        Name
                        <input name="name" defaultValue={row.name} required />
                      </label>
                      <label>
                        Tags (comma separated)
                        <input name="tags" defaultValue={(row.tags || []).join(", ")} />
                      </label>
                      <label>
                        Description
                        <textarea name="description" defaultValue={row.description} />
                      </label>
                      <label>
                        Credit
                        <textarea name="credit" defaultValue={row.credit} />
                      </label>
                      <label>
                        <input type="checkbox" name="approved" defaultChecked={row.approved} /> Approved
                        identity and reuse permission
                      </label>
                      <Button variant="secondary" disabled={busy}>
                        Save review
                      </Button>
                    </form>
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() =>
                        act(async () => {
                          await api(`/library/media/${row.id}`, { method: "DELETE" });
                          await reload();
                        })
                      }
                    >
                      Remove from future selection
                    </Button>
                  </>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function FolderImport({ selected, reload, onError }) {
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState("");
  const [rights, setRights] = useState(false);

  async function files(event) {
    const chosen = [...event.target.files];
    if (!rights) return;
    setBusy(true);
    const errors = [];
    let count = 0;
    for (const file of chosen) {
      if (!/\.(jpe?g|png|webp)$/i.test(file.name)) continue;
      const body = new FormData();
      body.set("file", file);
      body.set("name", file.name.slice(0, 160));
      body.set("creator", "Member supplied");
      body.set("rights_confirmed", "true");
      body.set("license", "Own work");
      try {
        await api(`/library/collections/${selected}/media`, { method: "POST", body });
        count++;
      } catch (e) {
        errors.push(`${file.name}: ${e.message}`);
      }
    }
    setReport(`${count} imported/reused. ${errors.join(" | ")}`);
    setBusy(false);
    await reload();
    event.target.value = "";
  }

  return (
    <section className="studio-card" style={{ marginBottom: 18 }}>
      <h3>Import Images</h3>
      <label className="checkbox-label">
        <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} /> I
        own these files and permit reuse and modification.
      </label>
      <div className="form-row">
        <label>
          Import Folder
          <input
            type="file"
            multiple
            webkitdirectory=""
            directory=""
            accept="image/jpeg,image/png,image/webp"
            disabled={busy || !rights}
            onChange={files}
          />
        </label>
        <label>
          Upload Images
          <input
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp"
            disabled={busy || !rights}
            onChange={files}
          />
        </label>
      </div>
      <p className="studio-subtext">
        One-time managed copies; no persistent folder synchronization.
      </p>
      <p role="status">{busy ? "Importing..." : report}</p>
      <details>
        <summary>Permitted local backend folder</summary>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setBusy(true);
            try {
              const r = await api(`/library/collections/${selected}/import-folder`, {
                method: "POST",
                body: JSON.stringify({ relative_path: f.get("path"), rights_confirmed: rights }),
              });
              setReport(r.files.map((x) => `${x.name}: ${x.error || "imported/reused"}`).join(" | "));
              await reload();
            } catch (err) {
              onError(err.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Relative subfolder
            <input name="path" placeholder="Optional subfolder under operator-permitted root" />
          </label>
          <Button disabled={busy || !rights}>Import local folder</Button>
        </form>
      </details>
    </section>
  );
}
