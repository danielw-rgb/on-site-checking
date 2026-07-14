# Crawl defaults

These are the standing defaults Claude applies to every Screaming Frog crawl in this project. Edit this file to change them — Claude reads it at the start of each crawl (step 0 of the Universal workflow in `CLAUDE.md`).

_Last updated: 2026-06-10_

## Profile values

Applied when scaffolding or loading a per-site profile in `./profiles/<domain-slug>.json`.

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
- **Recent crawl reuse** — in step 0c, if the most recent `<run-id>` in `./crawls/<domain-slug>/` is **within the last 2 days**, ask the user whether to reuse it via `sf_load_crawl` or start fresh. If older than 2 days, default to a fresh crawl without asking.

## How to change a default

Either:
1. **Tell Claude in chat** (e.g. "change max threads to 10") — Claude updates this file and the memory pointer.
2. **Edit this file directly** — Claude will read the new values on the next crawl.

If you change a value here, Claude does not retroactively update profiles already written under `./profiles/`. Those continue to use whatever was current when they were created, unless you ask Claude to refresh them.
