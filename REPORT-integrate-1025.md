# REPORT-integrate-1025

## TL;DR
- Branch `worktree-cf-integrate-1025` (opened from `worktree-cf-yokai-launch`) holds all 7 requested branches. Local only, nothing pushed.
- Full pytest: 2156 passed, 1 skipped, 1 failed (`test_multi_provider`, the known failure).
- `fable` / `yokai` / `technews` load; `produce.py --help` and `upload_pack.py --dry-run` both run (no upload).
- Open item: the 2026-10-24 pack's two technews `metadata.md` files still declare `chipcat` in their header, so the dry-run still routes them to chipcat. That is `output/` data (not committed); change the header to `（technews，…）`.

## Merges (in order)
| # | Branch | Result |
|---|---|---|
| 1 | cf-yokai-launch | fast-forward (base; carries brand-kit, fable, revisual, visual-v4, speed3, story-calibrate, technews, lanes-deadlock, stock-footage) |
| 2 | cf-fable-owl-fix | merged; CLAIMS.jsonl union |
| 3 | cf-thumbnail-v2 | merged; CLAIMS.jsonl union |
| 4 | cf-yt-uploader | merged; CLAIMS.jsonl union |
| 5 | cf-quality-v5 | merged; CLAIMS, `.pyc`, `test_wan_policy.py` conflicts (below) |
| 6 | cf-topic-radar | merged; CLAIMS.jsonl union |
| 7 | cf-deepsea-wan | merged; CLAIMS plus deck / lint / motion / motion_bake conflicts (below) |

## Conflict resolution
- `CLAIMS.jsonl` (every merge): union of lines, de-duplicated (58 lines at the end of merge 7).
- quality-v5 had committed `__pycache__/*.pyc` files that also exist in the base: took HEAD's copies. These should be untracked, but that is outside this task. I restored the tracked `.pyc` files that pytest rewrote, so they are not in my commits.
- `tests/unit/test_wan_policy.py`: took HEAD's version. It encodes revisual's always-on face-guard negative prompt and keeps the cache key of clips baked before the field existed; quality-v5's version asserts the same default and differs only in naming. The test passes.
- `explainer/deck.py`: kept both validators (shot_size / camera / lighting only on ai_image; wan_chain / wan_t2v need motion: wan).
- `explainer/lint.py`: the Wan-shot count uses deepsea-wan's `top = max(MAX_WAN_SHOTS, wan_budget)`; severity stays "warn" when there is no Wan shot at all (Leon 2026-10-24: avoid faces first). The `wan-face` check is kept.
- `explainer/motion.py`, `motion_bake.py`: the Wan request takes quality-v5's `shot_language.motion_prompt_for(...)` plus deepsea-wan's `chain=` and `t2v=`.
- Added `channels/styles/fable.md`: quality-v5's style files predate the fable channel, and its test requires one per AI-image channel. The content is taken from the fable.yaml `style_prefix` (warm picture-book, original animals only, no text).

Leon rules in force on the merged tree (all came in through the branches, no extra edits): review panel keeps script plus correctness only, facts and licensing use auto_fix_then_pass, Wan around 4 shots with 2 segments each, no faces on Wan shots, animals drawn without human hands.

## Channel mapping (settings)
| channel | YouTube channel | token env | display_name |
|---|---|---|---|
| fable | 不奇而寓 | `CF_YOUTUBE_REFRESH_TOKEN_FABLE` | 不奇而寓 |
| yokai | 怪談開談 | `CF_YOUTUBE_REFRESH_TOKEN_YOKAI` | 怪談開談 (provisional, **needs Leon's confirmation**) |
| technews | 晚點你就知道 | `CF_YOUTUBE_REFRESH_TOKEN` (default) | 晚點你就知道 |

- New optional `display_name` on the `youtube:` block of channel yaml (`production/channels.py`); the `refresh_token_env` values in the three yaml files now match the uploader's `CF_YOUTUBE_REFRESH_TOKEN_<CHANNEL>` naming (they used to be `CF_YT_*_REFRESH_TOKEN`). `channel_id_env` is unchanged.
- `youtube/channel_tokens.py`: `technews` is now its own channel and the `technews -> chipcat` alias is removed. Token resolution is `CF_YOUTUBE_REFRESH_TOKEN_TECHNEWS` if set, otherwise the default `CF_YOUTUBE_REFRESH_TOKEN`. Tests updated accordingly.
- technews no longer merges into 晶片貓: `technews.yaml` has its own series, identity and footer, and no "晶片貓快報" string exists in `src/`, `channels/` or `scripts/`. The only remaining "晶片貓快報" strings are in the committed `REPORT-yt-uploader.md`, `REPORT-brand-kit.md` and `artifacts/brand-kit/*`, plus the dated pack under `output/` (not committed). The channel's yaml `name` is still 科技新知 (series name used in on-screen cards); only `display_name` carries 晚點你就知道. Align them if wanted.

## Verification
- `pytest tests` with `PYTHONPATH=<worktree>/src`: **1 failed (test_multi_provider), 2156 passed, 1 skipped.** The first run also failed `test_shot_language_style` (missing fable style file), fixed as above.
- Channel load: `load_all()` returns fable / yokai / technews with the values in the table.
- `produce.py --help` runs. `upload_pack.py --dry-run --env-file ... --pack-dir output/upload-20261024` runs and uploads nothing (11 videos listed). It also flags two existing problems: the chipcat and deepsea long descriptions exceed 5000 bytes, and the day's quota need (17861) exceeds 10000.

## Side effects / cleanup
- Temp helper `fixclaims.py` is in the job tmp dir only. No files were left in the main checkout. No push, no paid service, no browser.
