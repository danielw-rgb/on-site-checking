# Crawl defaults

These are the standing defaults for every Screaming Frog crawl in this project. They are baked into the binary base config `crawl_default.seospiderconfig` (which is what actually drives crawls — see `screaming-frog/CLAUDE.md`). This file is the human-readable reference for what should be in that binary; keep the two in sync. When re-exporting the config from the SF UI, apply these values.

_Last updated: 2026-06-10_

## Baseline crawl values

Baked into `crawl_default.seospiderconfig`. (Also applied if you scaffold an optional per-site profile in `./profiles/<slug>.json`, but profiles are documentation only and don't push settings into SF.)

| Field | Value | Notes |
| --- | --- | --- |
| `max_crawl_depth` | `10` | Keep at or below 10 to avoid runaway crawls |
| `near_duplicates` | `true` | Near-duplicate detection on |
| `render_mode` | `text only` | No JavaScript rendering |
| `max_threads` | `5` | Concurrent crawl threads |
| Max URLs/sec | `2` | Rate cap. If stored as `crawl_delay_ms`, use `500` (≈2 URL/s) |

## Prompting rules

Override the Universal workflow defaults in `CLAUDE.md`:

- **Sitemap** — always ask the user to provide the sitemap URL before crawling. Do not auto-use `/sitemap.xml` or silently reuse a value stored in the profile. Even if `sitemap_urls` exists in the profile, confirm before each crawl.
- **Recent crawl reuse** — check `sf_list_crawls` for a crawl of this site already loaded in the SEO Spider. If one exists from **within the last 2 days**, ask the user whether to reuse it via `sf_load_crawl` or start fresh. If older than 2 days, default to a fresh crawl without asking.

## How to change a default

Either:
1. **Tell Claude in chat** (e.g. "change max threads to 10") — Claude updates this file and the memory pointer.
2. **Edit this file directly** — Claude will read the new values on the next crawl.

If you change a value here, Claude does not retroactively update profiles already written under `./profiles/`. Those continue to use whatever was current when they were created, unless you ask Claude to refresh them.
