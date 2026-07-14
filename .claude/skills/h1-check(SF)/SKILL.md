---
name: h1-check(SF)
description: Audit H1 tags across a crawled site — surfaces pages with missing, duplicate, or multiple H1 elements. Use when the user asks about H1 issues, heading structure, missing or repeated H1s, or pages with more than one H1.
requires:
  profile: {}
  exports:
    - slug: h1-missing
      source:
        type: seo_element
        element: H1
        filter: Missing
    - slug: h1-duplicate
      source:
        type: seo_element
        element: H1
        filter: Duplicate
    - slug: h1-multiple
      source:
        type: seo_element
        element: H1
        filter: Multiple
---

# H1 Check

Flags three H1 problem categories from a Screaming Frog crawl: pages with no H1, pages whose H1 duplicates another page's H1, and pages carrying more than one H1.

## When to use this skill

The user asks anything about:
- missing H1, no H1, pages without H1
- duplicate H1, repeated headings
- multiple H1s, more than one H1, multiple `<h1>` per page
- heading hierarchy or H1 SEO problems

## Prerequisites (from root CLAUDE.md)

Before this skill runs, the universal workflow in the root `CLAUDE.md` must already be complete for this run:

1. The user has provided `SITE_URL`.
2. `<domain-slug>` and `<run-id>` are set.
3. `sf_crawl` has completed (or `sf_load_crawl` reused a prior crawl).
4. The run manifest exists at `./screaming-frog/crawls/<domain-slug>/<run-id>/manifest.json`.

If any of those are missing, follow the root `CLAUDE.md` workflow first.

## Step 1 — Resolve exports (per CLAUDE.md step 4a)

The skill declares three exports in its frontmatter (`h1-missing`, `h1-duplicate`, `h1-multiple`), all sourced from `sf_export_seo_element_urls` with `element: h1`. For each one, CLAUDE.md's step 4a calls `manifest.js --has`, exports the NDJSON via `sf_export_seo_element_urls` if missing, and registers it in the manifest. Filter names match Screaming Frog's H1 tab — confirm via `sf_list_available_filters_for_seo_element` with `element: h1` if any export fails (filter labels can vary across SF versions; common alternates: "Missing" / "Duplicate" / "Multiple", lower- or title-cased).

After step 4a, the three files exist at:

- `./screaming-frog/crawls/<domain-slug>/<run-id>/h1-missing.ndjson`
- `./screaming-frog/crawls/<domain-slug>/<run-id>/h1-duplicate.ndjson`
- `./screaming-frog/crawls/<domain-slug>/<run-id>/h1-multiple.ndjson`

## Step 2 — Run the analyzer

From the project root:

```bash
node .claude/skills/h1-check/analyze-h1.js \
  --run-dir    ./screaming-frog/crawls/<domain-slug>/<run-id> \
  --output     ./screaming-frog/reports/<domain-slug>/<run-id>/h1-analysis.json
```

`--run-dir` is the crawl run folder; the analyzer reads the three `h1-*.ndjson` files from it. It writes the full JSON report to `--output`, a CSV table next to it (same path with `.csv` extension, overridable via `--csv <path>`), and prints a compact summary to stdout. You can invoke it via `sf_run_node_js_script` or the `Bash` tool.

**CSV layout:** one row per (URL, issue) pair. Columns: `URL`, `Issue`, `H1-1`, `H1-2` (matching the column names from the source SF NDJSON). `Issue` is `Missing H1` / `Duplicate H1` / `Multiple H1`. For `Missing H1`, both H1 columns are empty; for `Duplicate H1`, only `H1-1` is filled; for `Multiple H1`, both H1 columns are filled (when SF captured both). Open in Excel/Numbers/Sheets for triage.

## Step 3 — Interpret the output

Top-level keys in the JSON:

| Key | Meaning |
| --- | --- |
| `totals` | Per-category counts: pages missing an H1, pages with duplicate H1 strings, pages carrying multiple H1s. |
| `samples` | First 20 entries from each issue list — for quick triage. |
| `full` | Complete issue lists. |

Issue categories:

- **`missing`** — page has no `<h1>` element. High severity for content pages; low for redirects/utility pages.
- **`duplicate`** — page's H1 string is identical to one or more other crawled pages'. Often a templating bug or weak per-page metadata. Medium severity.
- **`multiple`** — page contains more than one `<h1>` element. Confusing heading hierarchy; flag for cleanup. Medium severity.

## Step 4 — Save the summary

Per the root `CLAUDE.md` "save the summary" rule, also write a human-readable summary to:

`./screaming-frog/reports/<domain-slug>/<run-id>/h1-summary.txt`

Include: site URL, crawl date, crawl ID, total pages crawled (from `manifest.json.total_urls_crawled`), counts per category, the top few example URLs from each category, and a pointer to `h1-analysis.json` for the full data.
