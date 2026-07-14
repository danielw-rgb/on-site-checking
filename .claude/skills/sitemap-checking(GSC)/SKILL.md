---
name: sitemap-checking(GSC)
description: Check whether the URLs in a site's XML sitemap appear in Google Search Console performance data (the "indexed" proxy) — flags sitemap URLs GSC has never shown, i.e. candidates for not-indexed / zero-impression pages. Use when the user asks whether sitemap pages are indexed, which submitted URLs aren't getting impressions, or to audit a sitemap against GSC.
---

# Sitemap Checking (GSC)

Fetches an XML sitemap (recursing into a sitemap index), then cross-checks every URL against
the pages GSC reported impressions for. A sitemap URL absent from GSC performance is flagged as
a candidate for **not indexed / zero impressions**.

> **Important approximation:** the Search Analytics API only knows pages that *got impressions*.
> It does **not** expose true index status, so "missing from GSC" means "not indexed **or**
> indexed-but-never-shown". Confirm flagged URLs with **URL Inspection** in the GSC UI.

## When to use this skill

- "are my sitemap pages indexed?", "which sitemap URLs aren't getting traffic?"
- audit a sitemap against GSC, find submitted URLs with no impressions
- this is also **check 4** inside `gsc-audit(GSC)` (that skill imports this analyzer).

## Step 0 — Bootstrap the shared workspace (first run in a project)

This skill is self-contained: it ships its own copy of the GSC connector + templates in
`_shared/`. On the **first** GSC skill you run in a project, materialise the shared workspace:

```bash
python3 ".claude/skills/sitemap-checking(GSC)/_shared/bootstrap.py"
```

This creates (only if absent — safe to re-run, and deduped when several GSC skills are installed):
`gsc/connector/gsc_fetch.py` (the shared connector), `gsc/requirements.txt`, `.env` (from the
template), `gsc/clients.example.json`, and `gsc/credentials/`. All GSC skills then share that one
connector + credentials store. The connector must live at `gsc/connector/gsc_fetch.py` — it
resolves `.env`, `gsc/credentials/`, and `gsc/clients.json` relative to its own location.

## Prerequisites (self-contained)

GSC is reached via the Search Console API with **OAuth installed-app** auth (agency logins, not
property owners). One "Desktop app" OAuth client works for all agency Google accounts. After
Step 0:

1. Fill `GSC_OAUTH_CLIENT_ID` + `GSC_OAUTH_CLIENT_SECRET` in `.env` (Google Cloud Console →
   Credentials → OAuth Desktop app). ⚠️ Set the consent screen to **"Production"**, not
   "Testing" — Testing-mode refresh tokens expire after 7 days.
2. `pip install -r gsc/requirements.txt`
3. Auth once per agency account: `python3 gsc/connector/gsc_fetch.py auth --account <slug>`

You also need the **sitemap URL** from the user (e.g. `https://www.example.com/sitemap.xml`).
This machine has no `python`; use `python3`. Fuller family rules live in `gsc/CLAUDE.md` if present.

## Step 1 — Gather inputs

1. **Account slug** (or `--client` in `gsc/clients.json`) and **property**.
2. **Sitemap URL** — the user provides it; the fetcher recurses into a `<sitemapindex>`.
3. **Client slug + date** for output paths.

## Step 2 — Pull the GSC page list (page dimension)

A `page`-dimension pull is the indexed/performing-page set (more complete than `query,page`,
which drops anonymized queries):

```bash
python gsc/connector/gsc_fetch.py query \
  --account <slug> --property <property> \
  --dimensions page \
  --date-from <YYYY-MM-DD> --date-to <YYYY-MM-DD> \
  --output gsc/sitemap-checking/data/<client>/<YYYY-MM-DD>_pages.ndjson
```

## Step 3 — Cross-check sitemap vs GSC

```bash
python ".claude/skills/sitemap-checking(GSC)/sitemap_index_check.py" \
  --sitemap <sitemap-url> \
  --pages   gsc/sitemap-checking/data/<client>/<YYYY-MM-DD>_pages.ndjson \
  --output  gsc/sitemap-checking/results/<client>/<YYYY-MM-DD>.json
```

Writes JSON (totals + missing URLs), a CSV of every missing URL, and a stdout summary. URLs are
normalized (scheme/`www`/trailing-slash/query/fragment) before matching.

## Step 4 — Save the summary

Write `gsc/sitemap-checking/results/<client>/<YYYY-MM-DD>_summary.md`: sitemap URL count, how many
appear in GSC vs missing, the top missing URLs, the approximation caveat, and a suggested next
step (URL-Inspect a sample; check for noindex/canonical/thin content on the missing ones).
