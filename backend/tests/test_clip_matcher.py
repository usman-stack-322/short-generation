import unittest

from backend.app.services.clip_matcher import (
    CelebrityProfile,
    ClipCandidate,
    detect_celebrities,
    plan_clip_timeline,
)


class TestClipMatcher(unittest.TestCase):
    def setUp(self):
        self.catalog = [
            CelebrityProfile(id="c1", name="LeBron James", slug="lebron-james", aliases=["King James", "LBJ", "LeBron"]),
            CelebrityProfile(id="c2", name="Stephen Curry", slug="stephen-curry", aliases=["Steph Curry", "Chef Curry"]),
        ]
        self.clips = [
            ClipCandidate(id="clip_1", celebrity_id="c1", r2_key="vault/lebron/1.mp4", duration_sec=12.0, tags=["interview", "espn"], usage_count=2),
            ClipCandidate(id="clip_2", celebrity_id="c1", r2_key="vault/lebron/2.mp4", duration_sec=10.0, tags=["dunk", "lakers"], usage_count=0),
            ClipCandidate(id="clip_3", celebrity_id="c2", r2_key="vault/curry/1.mp4", duration_sec=8.0, tags=["three", "warriors"], usage_count=1),
        ]

    def test_detects_celebrity_by_alias_in_order(self):
        script = "Chef Curry just responded to King James after the Lakers game."
        detected = detect_celebrities(script, self.catalog)
        self.assertEqual([c.name for c in detected], ["Stephen Curry", "LeBron James"])

    def test_prioritizes_tag_match_then_falls_back_to_least_used(self):
        script = "LeBron gave a wild ESPN interview last night about the playoffs."
        detected = detect_celebrities(script, self.catalog)
        timeline = plan_clip_timeline(script, target_duration_sec=10.0, matched_celebrities=detected, all_clips=self.clips, cut_length_sec=3.5)

        self.assertGreaterEqual(len(timeline), 3)
        self.assertEqual(timeline[0].clip_id, "clip_1")
        self.assertEqual(timeline[0].match_reason, "tag_match")
        self.assertEqual(timeline[1].clip_id, "clip_2")
        self.assertEqual(timeline[1].match_reason, "celebrity_fallback")
        self.assertAlmostEqual(sum(c.cut_duration_sec for c in timeline), 10.0, places=2)

    def test_graceful_fallback_when_celebrity_has_no_clips_in_vault(self):
        unknown_celeb = CelebrityProfile(id="c99", name="Kevin Durant", slug="kevin-durant", aliases=["KD"])
        timeline = plan_clip_timeline(
            "KD talks about USA Basketball.",
            target_duration_sec=7.0,
            matched_celebrities=[unknown_celeb],
            all_clips=self.clips,
            cut_length_sec=3.5,
        )
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0].match_reason, "vault_fallback")
        # Picks least-used clip across the vault (clip_2 has usage_count=0)
        self.assertEqual(timeline[0].clip_id, "clip_2")


if __name__ == "__main__":
    unittest.main()
