# Screaming Frog Family — Universal Workflow

These rules apply to all Screaming Frog-family skills (`h1-check`, `hreflang-analysis`, future SF skills). Every SF skill completes the shared crawl workflow below, then runs its own export + analysis.

Routing and the skills index live in the root `CLAUDE.md`. Skill files live at `.claude/skills/<skill-name>(SF)/SKILL.md`.

## Stateless by design — nothing is persisted to the repo

The Screaming Frog app (driven through the MCP) **is** the store of record for a crawl. Skills connect to the MCP, crawl (or reuse a loaded crawl), read the crawl result directly, and return findings **in chat**. They do **not** copy crawl files into the repo — no `crawls/`, no `reports/`, no run manifest. The only file a skill produces is a transient NDJSON export that the MCP writes into **its own base directory** (see step 3), which the analyzer then reads.

## Stack

- **Screaming Frog MCP** — runs crawls, exports element data, inspects URLs. Host-provided; see "MCP access" below. The SEO Spider app must be running and licensed on the host.
- **Node.js analyzers** — each skill's analyzer lives next to its `SKILL.md` at `.claude/skills/<name>(SF)/`. They read one NDJSON (via `--input <file>` or stdin) and print a JSON report to stdout — they write no files.

## MCP access (tool names are prefix-neutral)

Crawls and exports come from the **Screaming Frog MCP server** the host provides (in this repo, the `screaming-frog` entry in `.mcp.json`, an HTTP endpoint to a running SEO Spider). Refer to its tools by their **bare names** — `sf_crawl`, `sf_crawl_progress`, `sf_list_crawls`, `sf_load_crawl`, `sf_pause_crawl`, `sf_export_seo_element_urls`, `sf_list_available_filters_for_seo_element`, `sf_list_allowed_base_directory`, `sf_run_node_js_script`, etc. The **fully-qualified** name a model actually calls is `mcp__<server>__<tool>`, where `<server>` is whatever nickname the host registered the SF server under. Match the bare name against the SF tools available in your session — do not hardcode a prefix.

## Configuration: target URL

The target site URL is **provided by the user at the start of each run** (e.g. "audit https://example.com"). It is not stored in `.env` or any config file.

- **If the user has not provided a URL**, ask first. Do not guess, infer from prior runs, or fall back to a previously crawled site.
- **Normalize the URL**: ensure it includes a protocol (`https://` by default), strip any trailing slash, confirm if ambiguous. Treat it as `SITE_URL`.
- **Derive `<slug>`** from the hostname (strip protocol/port/path/query/fragment, lowercase, replace `.` with `-`; **do not strip `www.`**). It's only used to name the transient export file (e.g. `www-example-com-h1-all.ndjson`) so parallel runs don't collide.

## Universal workflow (always runs before any SF skill)

1. **Get the target URL** (see above). Ask if missing.
2. **Reuse or crawl.** Call `sf_list_crawls` to see what's already loaded in the SEO Spider (this — not a repo folder — is the source of truth for prior crawls). If a suitable recent crawl for this site exists, **ask the user** whether to reuse it (`sf_load_crawl` with its `instanceDirName`/`crawl_id`) or start fresh. To crawl fresh, call `sf_crawl` with `crawl_url: SITE_URL` and **always** `config_path: "screaming-frog/crawl_default.seospiderconfig"` (absolute path if the MCP's working dir differs from the repo). `sf_crawl` takes no inline crawl settings — sitemap/depth/near-duplicates/render/threads/delay are baked into that binary config. If the config file is missing, warn and ask whether to proceed with the GUI's loaded state or stop — never silently fall back.
3. **Wait until the crawl is not busy.** Poll `sf_crawl_progress` until `stateName` is no longer `SpiderActiveState` (finished, or `sf_pause_crawl` to stop a large crawl early — a partial crawl is fine, just tell the user it's partial). **Exports fail with "SEO Spider is busy" while a crawl is active**, so this wait is mandatory.
4. **Invoke the skill.** Match the user's intent to a skill in the root CLAUDE.md's Skills index, read that skill's `SKILL.md`, and run it. Each skill:
   - **Exports what it needs to the SF base directory.** The MCP caps string responses at ~100 kB, so exports must go to a file via `file_path`. That path is **relative to the SF server's base directory** (`sf_list_allowed_base_directory`), which is the MCP's own workspace — *not* the repo. The skill passes a `file_path` like `<slug>-<element>-all.ndjson`; the response's `path` field gives the absolute location.
   - **Reads the export directly and analyzes.** Run the skill's Node analyzer with `--input <that-path>` (the agent can read files in the SF base dir), or pipe the data on stdin, or run it inside the MCP via `sf_run_node_js_script`. The analyzer prints findings to stdout.
   - **Returns findings in chat.** No report file is written.

Skills use `sf_export_seo_element_urls` with `filter_name: "All"` (the MCP typically exposes only the `All` filter per element — confirm with `sf_list_available_filters_for_seo_element`) and let the analyzer do any issue classification. On an export failure, retry once; if it still fails, surface the error and stop — don't analyze partial/absent data.

## Crawl configuration (`crawl_default.seospiderconfig`)

`screaming-frog/crawl_default.seospiderconfig` is **the binary base config** — the only programmatic way to push reproducible settings into Screaming Frog through the MCP, since `sf_crawl` accepts no inline crawl-settings parameters.

- **Where it lives:** `screaming-frog/crawl_default.seospiderconfig`; pass it as `config_path` on every `sf_crawl`. It is committed so all collaborators crawl with identical baseline settings.
- **How to create / update it:** export from the Screaming Frog UI via **File → Configuration → Save As…**. `screaming-frog/CRAWL_DEFAULTS.md` is the human-readable reference; keep the two in sync.
- **Do not edit by hand** — it's a Screaming Frog–managed Java-serialized binary.
- **Site variants:** for site-specific tuning (e.g. deeper crawl for one large site), commit a pre-exported variant under `screaming-frog/configs/<name>.seospiderconfig` and pass that as `config_path`. Create variants on demand.

## Optional: per-site crawl profile

`screaming-frog/scripts/profile.js` can record per-site crawl intent (sitemap URL, depth, near-duplicates) as a gitignored JSON note under `screaming-frog/profiles/<slug>.json`. This is **optional convenience only** — profiles document settings but do **not** push them into SF (only the binary config does), and no skill requires one. Use it if the user wants to remember per-site settings between runs; otherwise skip it.

## Useful Screaming Frog MCP tools

- `sf_list_crawls` / `sf_load_crawl` — see what's loaded; re-load a prior crawl so a skill can export against it. This is how crawl reuse works (no repo folder scan).
- `sf_crawl` / `sf_crawl_progress` / `sf_pause_crawl` / `sf_resume_crawl` — run and control a crawl.
- `sf_list_available_filters_for_seo_element` — check which filters an element exposes (usually just `All`).
- `sf_export_seo_element_urls` — export one element's rows to an NDJSON file in the base dir (the skills' primary data source).
- `sf_list_allowed_base_directory` / `sf_read_text_file` / `sf_list_directories` — locate and read files in the MCP's base directory.
- `sf_run_node_js_script` — run a Node.js analyzer inside the MCP server (has direct access to the base-dir exports).
- `sf_url_info` / `sf_url_content` / `sf_url_links` / `sf_get_url_screenshot` — inspect a single URL deeply.
