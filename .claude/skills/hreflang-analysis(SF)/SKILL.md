---
name: hreflang-analysis(SF)
description: Audit hreflang annotations across a crawled site — detects missing x-default, duplicate locale entries, invalid language codes, missing self-references, and broken reciprocal return links. Use when the user asks about hreflang, international SEO, language targeting, or locale issues.
---

# Hreflang Analysis

Validates hreflang annotations (HTML `<link rel="alternate">`, HTTP `Link` headers, and sitemap entries) from a Screaming Frog crawl and surfaces international SEO issues.

This skill is **stateless** — it drives the Screaming Frog MCP and reads the crawl result directly. It writes **nothing** to the repo: the one export it needs goes to the SF server's own base directory, and the findings are returned in chat. Shared crawl mechanics live in `screaming-frog/CLAUDE.md` (read it once per session).

## When to use this skill

The user asks anything about:
- hreflang tags / annotations
- international SEO, multi-region or multi-language targeting
- locale issues, language codes, `x-default`
- "why doesn't Google serve the right page to users in country X"
- broken return links between language versions

## Step 1 — Get a crawl (per `screaming-frog/CLAUDE.md`)

Complete the shared crawl workflow first: get `SITE_URL`, then either reuse a crawl already loaded in the SEO Spider (`sf_list_crawls` → `sf_load_crawl`) or run a new one (`sf_crawl` with `config_path` pointing at `screaming-frog/crawl_default.seospiderconfig`). **Wait until the crawl has finished or is paused** — the MCP refuses exports while the Spider is busy (`sf_crawl_progress` state must not be `SpiderActiveState`).

## Step 2 — Export the hreflang data to the SF base directory

The MCP caps string responses at ~100 kB, so export to a file (it lands in the SF server's base dir, **not** the repo). Call `sf_export_seo_element_urls` with:

```json
{ "seo_element_name": "Hreflang", "filter_name": "All", "file_path": "<slug>-hreflang-all.ndjson" }
```

The response's `path` field is the absolute location of the NDJSON. Each row is one page carrying its hreflang annotations: `Address`, `Indexability`, and `HTML hreflang N` / `HTML hreflang N URL` (plus `HTTP …` and `Sitemap …`) locale+URL pairs — Screaming Frog's default column names, no extra config needed.

## Step 3 — Run the analyzer (reads the export, prints findings)

```bash
node ".claude/skills/hreflang-analysis(SF)/analyze-hreflang.js" \
  --input "<sf-base-dir>/<slug>-hreflang-all.ndjson" \
  --host  <crawl-host>
```

The analyzer reads that one NDJSON (or the same content piped on stdin) and prints a JSON report to stdout. It writes no files. You can also run it inside the MCP with `sf_run_node_js_script`.

`--host` is the hostname of the crawled site (e.g. `www.firstpage.hk`); it controls which destinations count as **external** (excluded from intra-crawl reciprocity). If omitted, it's derived from the first row's `Address`.

## Step 4 — Interpret the output

Top-level keys: `crawlHost`, `totals` (counts per category), `externalTargets` (hreflang destinations outside the crawl — reciprocity can't be auto-verified, flag for manual review), `samples`, `full`.

Issue categories:

- **`missingXDefault`** — page declares hreflang but no `x-default`. Google recommends one. Medium severity.
- **`duplicateLocale`** — same locale points to multiple distinct URLs from one page. Ambiguous; likely ignored. High severity.
- **`invalidLanguageCode`** — locale doesn't match a valid ISO 639 / 3166 pattern (e.g. `en_US` instead of `en-US`). High severity.
- **`selfNotInOwnSet`** — page doesn't reference itself under any locale. Every page in a hreflang group should self-reference. High severity.
- **`missingReturnLinkIntraCrawl`** — page A points to crawled page B, but B doesn't point back to A. hreflang requires bidirectional links. High severity.
- **`inconsistentReturnLinkIntraCrawl`** — A points to B as `xx-YY`, but B references A under a *different* locale. Medium severity.

## Step 5 — Report to the user (chat only)

Turn the JSON into a short plain-text summary: site URL, whether the crawl was full or partial (pages with hreflang), the per-category counts, top external target domains, and a few example URLs. Only mention categories that have findings. Do not write a report file — the SEO Spider holds the crawl, and this summary is the deliverable.
