import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Download, Film } from "lucide-react";
import { api, mediaUrl } from "../services/api";
import { PageHeader } from "../components/Shell";
import { Button, Loading, Notice } from "../components/UI";

export default function UploadHistory() {
  const [shortUploads, setShortUploads] = useState(null);
  const [error, setError] = useState("");
  const [banner, setBanner] = useState("");

  useEffect(() => {
    api("/title-shorts")
      .then((shorts) => {
        const exported = (shorts || []).filter(
          (s) => Boolean(s.video_url) || s.status === "ready"
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
        description="Download your rendered 9:16 MP4 Shorts and copy titles & scripts for manual publishing."
        action={
          <div className="studio-action-row">
            <Link to="/videos">
              <Button variant="secondary">All Videos</Button>
            </Link>
            <Link to="/title-to-short">
              <Button>Create Short</Button>
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
            <strong>No rendered MP4 exports yet</strong>
            <p>
              Render any Short in the Create Short studio to download the final 9:16 MP4 file here.
            </p>
            <Link to="/title-to-short">
              <Button>Create a Short</Button>
            </Link>
          </div>
        </section>
      ) : (
        <section className="studio-card">
          <div className="studio-card-head">
            <h2>
              <Film size={17} />
              <span>Rendered Exports ({shortUploads.length})</span>
            </h2>
          </div>

          <div className="table-wrap">
            <table className="studio-table">
              <thead>
                <tr>
                  <th>Short Title</th>
                  <th>Language</th>
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
                    <td>{item.language || "English"}</td>
                    <td>
                      <span className="studio-badge approved">
                        Ready for Download
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
