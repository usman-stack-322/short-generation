import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Download, Film, Lock } from "lucide-react";
import { api, mediaUrl } from "../services/api";
import { PageHeader } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";

export default function UploadHistory() {
  const role = localStorage.getItem("role") || "MEMBER";
  const isAdmin = ["OWNER", "ADMIN"].includes(role);
  const [shortUploads, setShortUploads] = useState(null);
  const [error, setError] = useState("");
  const [banner, setBanner] = useState("");

  useEffect(() => {
    api("/title-shorts")
      .then((shorts) => {
        const exported = (shorts || []).filter(
          (s) => s.review_status === "approved" || s.review_status === "uploaded"
        );
        setShortUploads(exported);
      })
      .catch((err) => setError(err.message));
  }, []);

  if (error && shortUploads === null) return <Notice>{error}</Notice>;
  if (shortUploads === null) return <Loading />;

  return (
    <div>
      <PageHeader
        eyebrow="MANUAL MP4 EXPORTS"
        title="Export History"
        description="Download approved 9:16 MP4 Shorts and copy titles & scripts for manual publishing."
        action={
          <div className="studio-action-row">
            {!isAdmin && (
              <span className="studio-lock-pill">
                <Lock size={12} />
                <span>Approval Required Before Download</span>
              </span>
            )}
            <Link to="/review-queue">
              <Button variant="secondary">Open Review Queue</Button>
            </Link>
          </div>
        }
      />

      {error && <Notice>{error}</Notice>}
      {banner && <Notice type="success">{banner}</Notice>}

      {shortUploads.length === 0 ? (
        <section className="studio-card">
          <div className="empty-state">
            <div className="empty-icon">
              <Download size={20} />
            </div>
            <strong>No approved exports yet</strong>
            <p>
              Once a rendered Short is approved in the Review Queue, its MP4 download unlocks here automatically.
            </p>
            <Link to="/review-queue">
              <Button>Go to Review Queue</Button>
            </Link>
          </div>
        </section>
      ) : (
        <section className="studio-card">
          <div className="studio-card-head">
            <h2>
              <Film size={17} />
              <span>Approved Exports ({shortUploads.length})</span>
            </h2>
          </div>

          <div className="table-wrap">
            <table className="studio-table">
              <thead>
                <tr>
                  <th>Short Title</th>
                  <th>Creator</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {shortUploads.map((item) => (
                  <tr key={`ts-${item.id}`}>
                    <td>
                      <Link to={`/title-to-short/${item.id}`} className="text-link">
                        {item.title}
                      </Link>
                    </td>
                    <td>{item.creator_name || "Title to Short"}</td>
                    <td>
                      <span className={`studio-badge ${item.review_status || "approved"}`}>
                        Approved for Download
                      </span>
                    </td>
                    <td>
                      <div className="studio-action-row">
                        {item.video_url && (
                          <a
                            href={mediaUrl(`${item.video_url}&download=true`)}
                            download={`short-${item.id}.mp4`}
                          >
                            <Button variant="secondary">
                              <Download size={13} />
                              <span>Download MP4</span>
                            </Button>
                          </a>
                        )}
                        <Button
                          variant="secondary"
                          type="button"
                          onClick={() => {
                            const text = `${item.title}\n\n${item.script || ""}\n\n#Shorts`;
                            navigator.clipboard
                              ?.writeText(text)
                              .then(() => setBanner(`Copied title & script for "${item.title}".`))
                              .catch(() => {});
                          }}
                        >
                          <span>Copy Title Pack</span>
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
