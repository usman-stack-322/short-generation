# Backend test failures — reconciled

**Status: all previously failing cases are resolved.** On 31 October 2026 every test file that appeared in the earlier failure list (previously 71 failed, 6 setup errors) was re-run in small batches and passed. No test was skipped, deselected or marked xfail to obtain this result.

Cause: the tests encoded superseded behaviour, not product defects. The current rules are:

- Channel access is strictly per-member (`channel_access` returns 404 to anyone but the channel's own member, including the workspace Owner).
- Roles are OWNER / ADMIN / MEMBER; `VIEWER` is no longer assignable (422), and members may create their own private channels.
- Registration creates a MEMBER; member creation returns `temporary_password`.

Most files had already been aligned with these rules (for example by using the `owner_publishable` fixture in `tests/conftest.py`). The last remaining cases were fixed in the tests only; no application code was changed:

| Test | Change |
|---|---|
| `test_auto_evergreen::test_channel_fallback_settings_persist_owner_only` | Uses `owner_publishable`; a non-owning editor is denied (403 or 404) |
| `test_remaining_fixes::test_scoped_personality_duplicates_concurrent` | Uses `owner_publishable`; the editor's private personality is unscoped because it cannot target the Owner's channel |
| `test_research_windows::test_retry_updates_same_job_persists_and_requires_explicit_generation` | Uses `owner_publishable` and acts as the channel's Owner |
| `test_safety::test_viewer_cannot_generate_or_regenerate_and_deactivation_revokes_access` | Asserts VIEWER is rejected (422); uses a fresh MEMBER; own-channel creation is allowed; deactivation still revokes access |

Verified batches (all passed):

1. `test_api`, `test_auto_evergreen`, `test_channel_analytics`, `test_day2_publishing`, `test_gemini_reliability`, `test_high_fixes`
2. `test_languages`, `test_live_configuration`, `test_quality_revision`, `test_real_photos`, `test_remaining_fixes`
3. `test_research_continuation`, `test_research_source_coverage`, `test_research_windows`
4. `test_review_drafts`, `test_risk_verification`, `test_safety`, `test_studio_completion`, `test_voice_director`, `test_workspace_privacy`

Not done: a single uninterrupted run of the entire backend suite. In this terminal that run times out, so verification is per file in batches. Run files in batches of 3-6 to reproduce.
