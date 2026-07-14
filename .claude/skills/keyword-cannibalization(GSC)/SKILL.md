---
name: keyword-cannibalization(GSC)
description: Detect keyword cannibalization from Google Search Console — flags search queries where 2+ of the site's own URLs compete, splitting clicks and rankings. Use when the user asks about keyword cannibalization, pages competing for the same query, multiple URLs ranking for one keyword, or which pages to consolidate/canonicalize.
---

# Keyword Cannibalization (GSC)

Pulls GSC Search Analytics data with `query` × `page` dimensions and flags queries where
two or more of the site's URLs each draw meaningful impressions — i.e. Google is serving
multiple pages for the same search, splitting authority and clicks.

## When to use this skill

The user asks anything about:
- keyword cannibalization, cannibalizing pages
- multiple pages / URLs ranking for the same keyword or query
- pages competing with each other in search
- which pages to merge, consolidate, canonicalize, or redirect

## Step 0 — Bootstrap the shared workspace (first run in a project)

This skill is self-contained: it ships its own copy of the GSC connector + templates in
`_shared/`. On the **first** GSC skill you run in a project, materialise the shared workspace:

```bash
python3 ".claude/skills/keyword-cannibalization(GSC)/_shared/bootstrap.py"
```

This creates (only if absent — safe to re-run, and deduped when several GSC skills are installed):
`gsc/connector/gsc_fetch.py` (the shared connector), `gsc/requirements.txt`, `.env` (from the
template), `gsc/clients.example.json`, and `gsc/credentials/`. All GSC skills then share that one
connector + credentials store. The connector must live at `gsc/connector/gsc_fetch.py` — it
resolves `.env`, `gsc/credentials/`, and `gsc/clients.json` relative to its own location.

## Prerequisites (self-contained)

GSC is reached via the Search Console API with **OAuth installed-app** auth (agency logins, not
property owners — a service account isn't viable). One "Desktop app" OAuth client works for all
agency Google accounts. After Step 0:

1. Fill `GSC_OAUTH_CLIENT_ID` + `GSC_OAUTH_CLIENT_SECRET` in `.env` (Google Cloud Console →
   Credentials → OAuth Desktop app). ⚠️ Set the consent screen to **"Production"**, not
   "Testing" — Testing-mode refresh tokens expire after 7 days.
2. `pip install -r gsc/requirements.txt`
3. Auth once per agency account (token cached in `gsc/credentials/`):
   `python3 gsc/connector/gsc_fetch.py auth --account <slug>`

If the token is missing, the connector prints the exact `auth` command to run — relay it. This
machine has no `python`; use `python3`. Fuller family rules live in `gsc/CLAUDE.md` if present.

## Step 1 — Gather required inputs (ask the user if missing)

1. **Account slug** — which agency Google login has access (`agency1`, `agency2`, …), OR a
   **`--client <slug>`** defined in `gsc/clients.json`.
2. **Property** — `sc-domain:example.com` or `https://www.example.com/` (skip if using `--client`).
3. **Date range** — default to the **last 3 months** ending ~3 days ago (GSC data lags). Longer
   ranges give more stable signals; note GSC caps history at 16 months.
4. **Thresholds (optional)** — `min-impressions` per page (default 10) and `min-pages` (default 2).

## Step 2 — Fetch query×page data via the connector

```bash
python gsc/connector/gsc_fetch.py query \
  --account <slug> --property <property> \
  --dimensions query,page \
  --date-from <YYYY-MM-DD> --date-to <YYYY-MM-DD> \
  --output gsc/keyword-cannibalization/data/<client>/<YYYY-MM-DD>.ndjson
```

(or `--client <slug>` in place of `--account` + `--property`). The connector paginates
automatically. `<client>` = short client slug (e.g. `bandletic`), used as the subfolder under
the skill's `data/` and `results/`. Same-day reruns append `_v2` to the date filename.

## Step 3 — Run the analyzer

```bash
python ".claude/skills/keyword-cannibalization(GSC)/analyze_cannibalization.py" \
  --input  gsc/keyword-cannibalization/data/<client>/<YYYY-MM-DD>.ndjson \
  --output gsc/keyword-cannibalization/results/<client>/<YYYY-MM-DD>.json \
  --min-impressions 10 --min-pages 2 \
  --exclude-query-regex '<brand>|site:'
```

Writes the JSON report, a CSV next to it (one row per competing query+page), and a stdout
summary. Tune `--min-impressions` up on large sites to cut noise.

**URL normalization (on by default — important):** GSC reports `#anchor` and `?query-string`
variants of the *same page* as separate rows, which otherwise fake cannibalization. The
analyzer strips both by default. Use `--keep-fragments` / `--keep-query` only if a site uses
them for genuinely distinct pages.

**Always pass `--exclude-query-regex`** with the site's brand term plus `site:` — brand and
`site:` searches legitimately surface many pages and would dominate the ranking. Check
`MEMORY.md` for the per-client brand term.

**Include non-English / transliterated brand variants in the regex.** A brand often appears in
more than one script (e.g. a Latin name plus its Chinese name and common misspellings). An
English-only pattern lets those variants leak through and re-flood the results with brand
navigational queries. Pass every known form, e.g. `--exclude-query-regex 'acme|阿克米|akmi|site:'`.

**Near-duplicate page patterns to expect.** Real cannibalization on these sites usually comes
from a page competing with a *near-copy* of itself. Watch for: a page vs its `/…-authenticity/`
(or `/…/authenticity/`) variant, a page vs its language-variant (`/en/…` or `…-en/`), Shopify
singular-vs-plural collections (`/collections/x-band` vs `/collections/x-bands`), and overlapping
`*-vs-*` comparison articles. These are consolidation/canonicalization candidates, not distinct pages.

## Step 4 — Interpret the output

Top-level JSON keys:

| Key | Meaning |
| --- | --- |
| `totals` | Row count, distinct queries, count of cannibalized queries, thresholds used. |
| `samples` | Top `--top` cannibalized queries by severity, for quick triage. |
| `full` | Every cannibalized query with its competing pages. |

Per finding: `num_pages` (competing URLs), `total_impressions`/`total_clicks`,
`impression_spread` (0 = one page dominates → 1 = evenly split, higher is worse),
`best_position`/`worst_position`, and `severity` (= total impressions × spread; rank
remediation by this). Each competing page lists its clicks, impressions, CTR, position.

Reading it: a high-severity query with two pages at similar positions and split impressions is
a strong consolidation candidate (canonicalize/redirect the weaker URL, or differentiate
intent). A query where one page dominates and another barely registers is usually benign.

## Step 5 — Save the summary

Write a human-readable summary to:

`gsc/keyword-cannibalization/results/<client>/<YYYY-MM-DD>_summary.md`

Include: property, account, date range, thresholds, total vs. cannibalized query counts, the
top ~10 offenders (query, competing URLs, impressions split, positions), a recommended action
per top offender (consolidate / differentiate / monitor), and a pointer to the JSON + CSV.

## Notes & limits

- GSC `query,page` rows omit the query for anonymized/rare searches, so true long-tail
  cannibalization is undercounted — that's a GSC privacy limit, not a bug.
- This is a single-snapshot view. Position **swapping over time** (the strongest cannibalization
  signal) is a planned phase 2: re-pull top offenders with a `date` dimension via the connector
  and chart position per URL. Flag to the user if they want that depth.
