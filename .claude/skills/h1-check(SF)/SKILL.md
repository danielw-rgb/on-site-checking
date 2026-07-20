---
name: h1-check(SF)
description: Audit H1 tags across a crawled site — surfaces pages with missing, duplicate, or multiple H1 elements. Use when the user asks about H1 issues, heading structure, missing or repeated H1s, or pages with more than one H1.
---

# H1 Check

Flags three H1 problem categories from a Screaming Frog crawl: pages with no H1, pages carrying more than one H1, and pages whose (indexable) H1 duplicates another page's H1.

This skill is **stateless** — it drives the Screaming Frog MCP and reads the crawl result directly. It writes **nothing** to the repo: the one export it needs goes to the SF server's own base directory, and the findings are returned in chat. Shared crawl mechanics live in `screaming-frog/CLAUDE.md` (read it once per session).

## When to use this skill

The user asks anything about:
- missing H1, no H1, pages without H1
- duplicate H1, repeated headings
- multiple H1s, more than one H1, multiple `<h1>` per page
- heading hierarchy or H1 SEO problems

## Step 1 — Get a crawl (per `screaming-frog/CLAUDE.md`)

Complete the shared crawl workflow first: get `SITE_URL`, then either reuse a crawl already loaded in the SEO Spider (`sf_list_crawls` → `sf_load_crawl`) or run a new one (`sf_crawl` with `config_path` pointing at `screaming-frog/crawl_default.seospiderconfig`). **Wait until the crawl has finished or is paused** — the MCP refuses exports while the Spider is busy (`sf_crawl_progress` state must not be `SpiderActiveState`).

## Step 2 — Export the H1 data to the SF base directory

The MCP caps string responses at ~100 kB, so export to a file (it lands in the SF server's base dir, **not** the repo). The MCP only exposes the `All` filter for H1 — the analyzer classifies missing / multiple / duplicate itself.

Call `sf_export_seo_element_urls` with:

```json
{ "seo_element_name": "H1", "filter_name": "All", "file_path": "<slug>-h1-all.ndjson" }
```

The response's `path` field is the absolute location of the NDJSON (e.g. `<sf-base-dir>/<slug>-h1-all.ndjson`). Each row has `Address`, `Occurrences`, `H1-1`, `H1-2`, `Indexability`.

## Step 3 — Run the analyzer (reads the export, prints findings)

```bash
node ".claude/skills/h1-check(SF)/analyze-h1.js" --input "<sf-base-dir>/<slug>-h1-all.ndjson"
```

The analyzer reads that one NDJSON (or the same content piped on stdin), classifies the three issue types, and prints a JSON report to stdout. It writes no files. You can also run it inside the MCP with `sf_run_node_js_script`.

Classification:
- **missing** — `H1-1` blank (page has no `<h1>`). High severity for content pages; low for redirects/utility pages.
- **multiple** — `Occurrences > 1` (more than one `<h1>`). Confusing heading hierarchy. Medium severity.
- **duplicate** — identical `H1-1` shared by 2+ **indexable** pages (non-indexable pages are excluded — a duplicate H1 there doesn't cost rankings). Grouped into clusters, largest first. Medium severity.

## Step 4 — Report to the user (chat only)

Turn the JSON `totals` and `samples` into a short plain-text summary: site URL, whether the crawl was full or partial (pages analyzed), the per-category counts, and the top few example URLs / duplicate clusters. Only mention categories that have findings. Do not write a report file — the SEO Spider holds the crawl, and this summary is the deliverable.
