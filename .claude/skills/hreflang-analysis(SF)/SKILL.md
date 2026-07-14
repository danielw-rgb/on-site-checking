---
name: hreflang-analysis(SF)
description: Audit hreflang annotations across a crawled site — detects missing x-default, duplicate locale entries, invalid language codes, missing self-references, and broken reciprocal return links. Use when the user asks about hreflang, international SEO, language targeting, or locale issues.
requires:
  profile: {}
  exports:
    - slug: hreflang-contains
      source:
        type: bulk_export
        name: "Hreflang:Contains Hreflang"
---

# Hreflang Analysis

Validates hreflang annotations (HTML `<link rel="alternate">`, HTTP `Link` headers, and sitemap entries) from a Screaming Frog crawl and surfaces international SEO issues.

## When to use this skill

The user asks anything about:
- hreflang tags / annotations
- international SEO, multi-region or multi-language targeting
- locale issues, language codes, `x-default`
- "why doesn't Google serve the right page to users in country X"
- broken return links between language versions

## Prerequisites (from root CLAUDE.md)

Before this skill runs, the universal workflow in the root `CLAUDE.md` must already be complete for this run:

1. The user has provided `SITE_URL`.
2. `<domain-slug>` and `<run-id>` have been set.
3. `sf_crawl` has completed (or `sf_load_crawl` reused a prior crawl).

If any of those are missing, follow the root `CLAUDE.md` workflow first.

## Step 1 — Export the hreflang annotation NDJSON

The analyzer needs a per-page export where each row carries all hreflang annotations declared for that page (HTML, HTTP header, sitemap), with locale + URL pairs.

1. Call `sf_list_available_bulk_exports` to see the current crawl's available exports.
2. Look for the Hreflang-related bulk export(s) (typical names: `Hreflang:All` or filters under the `Hreflang` tab such as `Hreflang:Contains Hreflang`). Don't hard-code the name — the available set varies by crawl mode and config.
3. Call `sf_generate_bulk_export` to write the NDJSON to:
   `./screaming-frog/crawls/<domain-slug>/<run-id>/hreflang-contains.ndjson`
   (Use `.ndjson` so each row is one JSON object — that's what the analyzer expects.)

Each row must contain `Address` plus fields like `HTML hreflang 1`, `HTML hreflang 1 URL`, `HTTP hreflang 1`, `HTTP hreflang 1 URL`, `Sitemap hreflang 1`, `Sitemap hreflang 1 URL`, etc. (up to 50 per source). Those are Screaming Frog's default column names — no extra config needed.

## Step 2 — Run the analyzer

From the project root:

```bash
node .claude/skills/hreflang-analysis/analyze-hreflang.js \
  --input  ./screaming-frog/crawls/<domain-slug>/<run-id>/hreflang-contains.ndjson \
  --output ./screaming-frog/reports/<domain-slug>/<run-id>/hreflang-analysis.json \
  --host   <crawl-host>
```

`--host` is the hostname of the crawled site (e.g. `www.firstpage.hk`). It controls which destinations are treated as **external** (excluded from intra-crawl reciprocity checks). If you omit it, the analyzer derives it from the first row's `Address`.

The script writes the full JSON report to `--output` and prints a compact summary to stdout.

You can invoke it via `sf_run_node_js_script` or directly via the `Bash` tool — either works.

## Step 3 — Interpret the output

Top-level keys in the JSON:

| Key | Meaning |
| --- | --- |
| `crawlHost` | The host used to separate intra-crawl vs external destinations. |
| `totals` | Counts per issue category. |
| `externalTargets` | Domains referenced by hreflang but outside the crawl, with hit counts. Reciprocity can't be verified for these — flag for manual review. |
| `samples` | First N entries from each issue list (10 for most, 20 for return-link issues). Useful for quick triage. |
| `full` | Complete issue lists. |

Issue categories:

- **`missingXDefault`** — page declares hreflang but no `x-default`. Google recommends one. Medium severity.
- **`duplicateLocale`** — same locale points to multiple distinct URLs from the same page. Ambiguous and will likely be ignored by search engines. High severity.
- **`invalidLanguageCode`** — locale doesn't match a valid ISO 639 / 3166 pattern (e.g. `en_US` instead of `en-US`, or `gb` instead of `en-GB`). High severity.
- **`selfNotInOwnSet`** — page doesn't reference itself under any locale. Every page in a hreflang group should self-reference. High severity.
- **`missingReturnLinkIntraCrawl`** — page A points to crawled page B, but B doesn't point back to A. hreflang requires bidirectional links. High severity.
- **`inconsistentReturnLinkIntraCrawl`** — A points to B as `xx-YY`, but B references A under a *different* locale. Confusing for search engines. Medium severity.

## Step 4 — Save the summary

Per the root `CLAUDE.md` "save the summary" rule, also write a human-readable summary to:

`./screaming-frog/reports/<domain-slug>/<run-id>/hreflang-summary.txt`

Include: site URL, crawl date, crawl ID, total pages with hreflang, counts per issue category, the top external target domains, and a pointer to `hreflang-analysis.json` for the full data.
