# Screaming Frog Family — Universal Workflow

These rules apply to all Screaming Frog-family skills (`h1-check`, `hreflang-analysis`, future SF skills). Every SF skill **must** complete the universal workflow below before its own analysis steps.

Routing and the skills index live in the root `CLAUDE.md`. Skill files live at `.claude/skills/<skill-name>/SKILL.md` (at the project root, not under `screaming-frog/`).

## Stack

- **Screaming Frog MCP** (`mcp__screaming-frog__*`) — runs crawls, exports reports, analyses results.
- **Node.js helpers** — `screaming-frog/scripts/profile.js` and `manifest.js` are cross-skill. Skill-specific analyzers live next to their `SKILL.md`.

## Configuration: target URL

The target site URL is **provided by the user at the start of each run** (e.g. "audit https://example.com"). It is not stored in `.env` or any config file.

- **If the user has not provided a URL**, ask first. Do not guess, infer from prior runs, or fall back to a previously crawled site. Typical prompt: *"What's the target site URL you'd like to crawl? (full URL with protocol, e.g. `https://example.com`)"*
- **Normalize the URL**: ensure it includes a protocol (`https://` by default), strip any trailing slash, and confirm with the user if there was ambiguity (e.g. they typed `example.com` and you assumed `https://`).
- **Treat this as `SITE_URL`** — pass it to `sf_crawl` and use it to derive `<domain-slug>` (see "Run identity" below). For any Node.js scripts that need it, pass the URL as an argument.

## Crawl profile (per-site)

Crawl options that vary between sites (sitemap URL, crawl depth, near-duplicates, include/exclude patterns, custom extractions, render mode, thread count) live in `screaming-frog/profiles/<domain-slug>.json`. The binary `screaming-frog/crawl_default.seospiderconfig` is the base SF config (the only programmatic way to push settings into Screaming Frog through the MCP); the profile JSON layers on top per site as documentation/snapshot, since `sf_crawl` accepts no inline settings.

- **Why per-site:** each site has stable settings of its own. Persisting avoids re-prompting on every re-audit.
- **Authoritative schema:** see `DEFAULTS` in `screaming-frog/scripts/profile.js`. Fields: `site_url`, `sitemap_urls`, `max_crawl_depth` (default 10; keep ≤ 10 to avoid infinite crawls), `near_duplicates`, `include_patterns`, `exclude_patterns`, `custom_extractions`, `render_mode`, `max_threads`, `crawl_delay_ms`, `last_updated`.
- **Helper script:** `node screaming-frog/scripts/profile.js`
  - `--load <slug>` → prints the profile JSON, exits 1 if missing.
  - `--init <slug>` → scaffolds a defaults-only profile if none exists.
  - `--save <slug>` → reads JSON from stdin, merges with defaults, stamps `last_updated`, writes.
  - `--check <slug> <skill-name>` → exits 0 if the profile satisfies the skill's `requires.profile` block, 1 otherwise (prints missing fields).
- **Editing:** Claude updates the profile from the user's prompt (e.g. "set crawl depth to 5"). Don't ask the user to edit the JSON by hand.
- **Not committed (regenerable workspace):** `screaming-frog/profiles/` is gitignored. The profile JSON does not push settings into Screaming Frog (only the binary `crawl_default.seospiderconfig` does — see below), so it carries no reproducibility value worth sharing. It is created on demand per run and stays local.

## Run identity

Every run gets a stable identity composed once at the start of the run and reused across every export, report, and summary:

- **`<domain-slug>`** — derived from `SITE_URL`. Take the hostname (strip protocol, port, path, query, fragment), lowercase, replace `.` with `-`. **Do not strip `www.`** — keep the slug faithful to what was crawled so `www.example.com` and `example.com` don't collide. Examples: `https://www.example.com` → `www-example-com`; `https://shop.example.co.uk` → `shop-example-co-uk`.
- **`<run-id>`** — `<YYYY-MM-DD>_<HH-MM-SS>` captured in local time at the moment `sf_crawl` is kicked off (or, when reusing a prior crawl via `sf_load_crawl`, at the moment the reuse decision is made). Reuse the same `<run-id>` for `crawls/`, `reports/`, and the summary file so they line up.

When reusing a previously loaded crawl, treat the reuse as its own run with a fresh `<run-id>` — exports and summaries from the reuse go into a new folder.

**Invariant:** every run ends with files in `screaming-frog/crawls/<domain-slug>/<run-id>/` and `screaming-frog/reports/<domain-slug>/<run-id>/`. If those folders are empty after a run, the run is incomplete — re-export before drawing conclusions.

## Universal workflow (always runs before any SF skill)

0. **Get the target URL.** If missing, ask (see "Configuration" above). Then:
   - **0a. Derive `<domain-slug>`** from `SITE_URL`.
   - **0b. Load or create the crawl profile.** Run `node screaming-frog/scripts/profile.js --load <domain-slug>`. If it exits 1 (no profile yet), ask the user for sitemap URL, crawl depth (default 10, keep ≤ 10), and near-duplicates on/off — plus any other prompt-settable fields — then save with `--save`. If a profile already exists, show its current values to the user and ask whether to confirm or change anything before crawling.
   - **0c. Check for an existing crawl** by inspecting `screaming-frog/crawls/<domain-slug>/` for prior runs (subfolders are `<run-id>`s; sort descending for the most recent). Also call `sf_list_crawls` to see what is loaded in the SEO Spider. If a recent crawl exists, **ask the user** whether to:
     - **Reuse the previous crawl** — call `sf_load_crawl` with the existing `crawl_id` and skip step 1.
     - **Start a new crawl** — proceed to step 1.
1. **Crawl** — `sf_crawl` against `SITE_URL`. **Always pass `config_path: "screaming-frog/crawl_default.seospiderconfig"`** so the crawl uses reproducible settings. `sf_crawl` accepts no inline crawl-settings parameters — sitemap, depth, near-duplicates, render mode, threads, delay are baked into the `.seospiderconfig` binary. The per-site profile JSON is documentation + snapshot only. If a site needs different settings, ask the user to re-export the binary (or maintain a per-site `screaming-frog/configs/<variant>.seospiderconfig`). Poll `sf_crawl_progress` until done.
2. **Write the run manifest (always — never skipped).** Exports are produced lazily by the skills that need them. This step only records what was crawled:
   - **Create folders** if absent: `screaming-frog/crawls/<domain-slug>/<run-id>/` and `screaming-frog/reports/<domain-slug>/<run-id>/`.
   - **Write `manifest.json`:** call `node screaming-frog/scripts/manifest.js --init <domain-slug> <run-id>` and pipe the crawl metadata JSON on stdin: `{site_url, sf_crawl_id, crawl_started_at, crawl_finished_at, total_urls_crawled, profile_snapshot}`. `profile_snapshot` is the full profile JSON loaded in step 0b. The manifest is written with `exports: []`; skills append to it in step 4a.
   - **Do not pre-export NDJSONs here.** No `sf_export_crawl`, no enumerated bulk exports, no reports. Skills declare what they need via `requires.exports` in their `SKILL.md` and produce only those files when invoked.
3. **Verify skill requirements.** Before running the skill, read its `SKILL.md` frontmatter and check the optional `requires:` block. Run `node screaming-frog/scripts/profile.js --check <domain-slug> <skill-name>`. If it exits 1, the profile doesn't satisfy the skill's `requires.profile` constraints — **stop and ask the user** whether to update the profile and re-crawl. Do not auto-enable settings.
4. **Invoke the skill** — match the user's intent to a skill in the root CLAUDE.md's Skills index, read that skill's `SKILL.md`, and execute its workflow.
   - **4a. Resolve exports (always — runs before the skill's own steps).** For each entry in the skill's `requires.exports`:
     1. Get the list: `node screaming-frog/scripts/manifest.js --skill-exports <skill-name>` returns the `[{slug, source}, ...]` array.
     2. Ensure the crawl is loaded in Screaming Frog: call `sf_list_crawls`; if the run's `sf_crawl_id` isn't loaded, call `sf_load_crawl`.
     3. Per export entry, check reuse: `node screaming-frog/scripts/manifest.js --has <domain-slug> <run-id> <export-slug>`. If exit 0, the NDJSON is already on disk and tracked — skip to the next entry.
     4. If exit 1, generate the NDJSON into `screaming-frog/crawls/<domain-slug>/<run-id>/<export-slug>.ndjson`:
        - `source.type === "bulk_export"` → `sf_generate_bulk_export` with `bulk_export_name: source.name`.
        - `source.type === "seo_element"` → `sf_export_seo_element_urls` with `element: source.element` and `filter: source.filter`.
     5. Record it: pipe `{filename, source, row_count, exported_by_skill}` on stdin to `node screaming-frog/scripts/manifest.js --add <domain-slug> <run-id> <export-slug>`.
     6. **Failure rule:** if any export call fails, retry once; if it still fails, surface the error to the user and **stop** — do not run the analyzer with partial data.
5. **Save the summary.** Whenever a skill (or you, in a one-off analysis) produces a written finding for the user, also save it as a plain-text `.txt` file under `screaming-frog/reports/<domain-slug>/<run-id>/` so the user has a durable record. Name it descriptively (e.g. `hreflang-summary.txt`, `redirect-chains-summary.txt`, `full-audit-summary.txt`). Include: site URL, crawl date, crawl ID, total URLs crawled, the counts/findings, and pointers to the raw export files the summary was derived from.

## Crawl configuration (`crawl_default.seospiderconfig`)

`screaming-frog/crawl_default.seospiderconfig` is **the binary base config** — the only programmatic way to push settings into Screaming Frog through the MCP, since `sf_crawl` accepts no inline crawl-settings parameters.

- **Where it lives:** `screaming-frog/crawl_default.seospiderconfig`. The MCP's `config_path` argument accepts the path `"screaming-frog/crawl_default.seospiderconfig"`.
- **How to create / update it:** export from the Screaming Frog UI via **File → Configuration → Save As…** after configuring the desired settings. `screaming-frog/CRAWL_DEFAULTS.md` is the human-readable reference for what should be baked in; keep the two in sync when defaults change.
- **How the MCP uses it:** every `sf_crawl` call must include `config_path: "screaming-frog/crawl_default.seospiderconfig"`. If the file is missing, warn the user and ask whether to (a) proceed with whatever the SF GUI has loaded or (b) stop so the user can re-export one. Do **not** silently fall back to GUI state.
- **Do not edit by hand** — it's a Screaming Frog–managed Java-serialized binary. Re-export from the UI to change settings.
- **`screaming-frog/configs/` variants:** for site-specific tuning (e.g. deeper crawl for one large site), commit a pre-exported variant under `screaming-frog/configs/<variant-name>.seospiderconfig` and reference it in that site's profile. Create variants on demand, not upfront.
- **Profile JSON ≠ pushed settings:** `screaming-frog/profiles/<slug>.json` records intent and gets snapshotted into the run manifest, but it does NOT push values into SF. Reproducibility comes from the binary config.

## Folder conventions

- `screaming-frog/crawls/<domain-slug>/<run-id>/` — per-run crawl store. Always contains `manifest.json` (written in step 2). NDJSON export files are added lazily by skills (one per issue category, e.g. `hreflang-contains.ndjson`, `h1-missing.ndjson`); the manifest's `exports` array indexes what's been produced. Filenames use hyphenated kebab-case.
- `screaming-frog/reports/<domain-slug>/<run-id>/` — generated reports and human-readable `.txt` summaries (mirror layout of `crawls/`).
- `screaming-frog/profiles/<domain-slug>.json` — per-site crawl profile. Gitignored (regenerated on demand; does not push SF settings).
- `screaming-frog/scripts/` — cross-skill helpers (`profile.js`, `manifest.js`). **Skill-specific scripts live inside the skill folder at `.claude/skills/<name>/`, not here.**
- `screaming-frog/configs/` — site-specific pre-exported `.seospiderconfig` variants. Committed. Empty until a site needs settings beyond the base config.
- `screaming-frog/crawls/` is gitignored (regenerable from the SF crawl ID + config).
- `screaming-frog/crawl_default.seospiderconfig` **is committed** so all collaborators crawl with identical baseline settings.

## Useful Screaming Frog MCP tools

- `sf_list_crawls` / `sf_load_crawl` — check which crawls are loaded in the SF session; re-load a prior run so a skill can produce new exports against it (used in step 4a).
- `sf_list_available_reports` / `sf_list_available_bulk_exports` — discover what can be exported.
- `sf_list_available_filters_for_seo_element` — find issue filters per element (e.g. response codes, page titles).
- `sf_generate_bulk_export` / `sf_export_seo_element_urls` — produce a single NDJSON export. Skills invoke these in step 4a per their `requires.exports`.
- `sf_url_info` / `sf_url_content` / `sf_url_links` — inspect a single URL deeply.
- `sf_get_url_screenshot` — visual check of a rendered page.
- `sf_run_node_js_script` — run a Node.js script inside the MCP server (good for skill analyzers).
