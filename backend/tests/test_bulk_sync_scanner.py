from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts.bulk_sync_r2 import compute_fast_hash, run_sync, scan_vault_folder


class TestBulkSyncScanner(unittest.TestCase):
    def _build_sample_vault(self, root: Path) -> tuple[Path, Path]:
        lebron_dir = root / "LeBron James"
        curry_dir = root / "Stephen Curry"
        lebron_dir.mkdir(parents=True)
        curry_dir.mkdir(parents=True)

        clip_a = lebron_dir / "espn_interview_2025.mp4"
        clip_b = curry_dir / "warriors_tunnel_walk.mp4"

        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=1280x720:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_a)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=gold:s=720x1280:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_b)],
            check=True,
            capture_output=True,
        )
        return clip_a, clip_b

    def test_scans_folders_extracts_ffprobe_metadata_and_supports_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Celebrities"
            clip_a, _ = self._build_sample_vault(root)

            scanned = scan_vault_folder(root)
            self.assertEqual(len(scanned), 2)

            by_slug = {c.celebrity_slug: c for c in scanned}
            self.assertEqual(by_slug["lebron-james"].aspect_ratio, "16:9")
            self.assertEqual(by_slug["lebron-james"].width, 1280)
            self.assertIn("interview", by_slug["lebron-james"].tags)

            self.assertEqual(by_slug["stephen-curry"].aspect_ratio, "9:16")
            self.assertEqual(by_slug["stephen-curry"].height, 1280)
            self.assertAlmostEqual(by_slug["stephen-curry"].duration_sec, 2.0, delta=0.3)

            # Hash must be deterministic for resume support
            self.assertEqual(compute_fast_hash(clip_a), by_slug["lebron-james"].file_hash)

            summary = run_sync(
                root_dir=root,
                api_base_url=None,
                category="NBA",
                dry_run=True,
                checkpoint_path=Path(tmp) / "checkpoint.json",
            )
            self.assertEqual(summary["total_clips_found"], 2)
            self.assertEqual(summary["pending_upload"], 2)
            self.assertTrue(summary["dry_run"])

    def test_local_only_mode_uses_local_uri_and_indexes_without_r2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Celebrities"
            clip_a, clip_b = self._build_sample_vault(root)
            checkpoint = Path(tmp) / "sync_checkpoint.json"

            scanned = scan_vault_folder(root, local_only=True)
            by_slug = {c.celebrity_slug: c for c in scanned}
            self.assertEqual(by_slug["lebron-james"].r2_key, f"local://{clip_a.resolve().as_posix()}")
            self.assertEqual(by_slug["stephen-curry"].r2_key, f"local://{clip_b.resolve().as_posix()}")

            mock_resp = MagicMock()
            mock_resp.json.return_value = {"inserted": 2, "skipped_existing": 0, "celebrities_created": 2}
            mock_resp.raise_for_status.return_value = None

            with patch("httpx.post", return_value=mock_resp) as post_mock, patch(
                "backend.app.services.r2_storage.R2StorageService",
                side_effect=AssertionError("R2 must not be called in --local-only mode"),
            ):
                summary = run_sync(
                    root_dir=root,
                    api_base_url="http://127.0.0.1:8000",
                    category="NBA",
                    dry_run=False,
                    checkpoint_path=checkpoint,
                    local_only=True,
                )

            self.assertEqual(summary["storage_mode"], "local")
            self.assertEqual(summary["synced_now"], 2)
            self.assertEqual(summary["inserted_total"], 2)
            self.assertTrue(checkpoint.exists())
            post_mock.assert_called_once()
            sent_clips = post_mock.call_args.kwargs["json"]["clips"]
            self.assertTrue(all(c["r2_key"].startswith("local://") for c in sent_clips))

            # Second run resumes cleanly from checkpoint without re-posting
            with patch("httpx.post") as second_post:
                resumed = run_sync(
                    root_dir=root,
                    api_base_url="http://127.0.0.1:8000",
                    category="NBA",
                    dry_run=False,
                    checkpoint_path=checkpoint,
                    local_only=True,
                )
            second_post.assert_not_called()
            self.assertEqual(resumed["already_synced"], 2)
            self.assertEqual(resumed["pending_upload"], 0)


if __name__ == "__main__":
    unittest.main()
