---
name: gsc-audit(GSC)
description: Run a full Google Search Console audit — cannibalization, low-hanging-fruit (striking-distance) keywords, CTR opportunities, index hygiene (pages indexed but shouldn't be), outdated content, and sitemap indexing — and produce ONE combined report. Use when the user wants a full GSC checkup / health report, or several GSC checks at once in a single document.
---

# GSC Audit (GSC)

Runs six GSC checks off shared pulls and writes **one** combined report (summary + top-N table
per check + a per-check CSV). Composes the `keyword-cannibalization(GSC)` and
`sitemap-checking(GSC)` analyzers — this is the intended composition point for those skills.

| # | Check | Data |
| --- | --- | --- |
| 1 | Keyword cannibalization | query×page |
| 2 | Low-hanging fruit (pos 4–20) | query×page |
| 3 | CTR opportunity (good pos, low CTR) | query×page |
| 4 | Index hygiene (indexed but shouldn't be) | page |
| 5 | Outdated content (old year still ranking) | query×page |
| 6 | Sitemap indexing (in sitemap, missing from GSC) | page + sitemap |

## When to use this skill

- "run a full GSC audit / checkup / health report"
- the user wants several of the checks above together in one document
- For a single check in isolation, use that check's own skill instead.

## Step 0 — Bootstrap the shared workspace (first run in a project)

This skill is self-contained: it ships its own copy of the GSC connector + templates in
`_shared/`. On the **first** GSC skill you run in a project, materialise the shared workspace:

```bash
python3 ".claude/skills/gsc-audit(GSC)/_shared/bootstrap.py"
```

This creates (only if absent — safe to re-run, and deduped when several GSC skills are installed):
`gsc/connector/gsc_fetch.py` (the shared connector), `gsc/requirements.txt`, `.env` (from the
template), `gsc/clients.example.json`, and `gsc/credentials/`. All GSC skills then share that one
connector + credentials store. The connector must live at `gsc/connector/gsc_fetch.py` — it
resolves `.env`, `gsc/credentials/`, and `gsc/clients.json` relative to its own location.

## Prerequisites (self-contained)

GSC is reached via the Search Console API with **OAuth installed-app** auth (we are an agency,
not property owners, so a service account isn't viable). One "Desktop app" OAuth client works
for **all** agency Google accounts; the account that *consents* determines which properties are
visible. After Step 0:

1. Fill `GSC_OAUTH_CLIENT_ID` + `GSC_OAUTH_CLIENT_SECRET` in `.env` (Google Cloud Console →
   Credentials → OAuth Desktop app). ⚠️ Set the consent screen to **"Production"**, not
   "Testing" — Testing-mode refresh tokens expire after 7 days.
2. `pip install -r gsc/requirements.txt`
3. Auth once per agency account (token cached in `gsc/credentials/`, no re-login after):
   `python3 gsc/connector/gsc_fetch.py auth --account <slug>`

This machine has no `python`; use `python3`. Fuller family rules live in `gsc/CLAUDE.md` if
present. Then gather: account/property (or `--client`), client slug, date range, and optionally
the **sitemap URL** (for check 6) and the **brand term** (to exclude from cannibalization).

## Step 1 — Assemble the data (reuse before re-pulling)

Two pulls feed all six checks. **Reuse existing NDJSON when it's fresh** (e.g. a recent
`keyword_cannibalization` pull is a valid query×page source) — only pull what's missing.

```bash
# query×page (checks 1,2,3,5) — REUSE an existing pull if available
python gsc/connector/gsc_fetch.py query --account <slug> --property <property> \
  --dimensions query,page --date-from <from> --date-to <to> \
  --output gsc/gsc-audit/data/<client>/<date>_query-page.ndjson

# page (checks 4,6) — includes anonymized-query impressions that query×page drops
python gsc/connector/gsc_fetch.py query --account <slug> --property <property> \
  --dimensions page --date-from <from> --date-to <to> \
  --output gsc/gsc-audit/data/<client>/<date>_pages.ndjson
```

## Step 2 — Run the audit

```bash
python ".claude/skills/gsc-audit(GSC)/gsc_audit.py" \
  --client <client> --date <YYYY-MM-DD> \
  --query-page gsc/gsc-audit/data/<client>/<date>_query-page.ndjson \
  --pages      gsc/gsc-audit/data/<client>/<date>_pages.ndjson \
  --sitemap    <sitemap-url> \
  --base       https://<domain> \
  --brand-regex '<brand>|site:' \
  --property   <property> --date-range "<from> → <to>" \
  --outdir     gsc/gsc-audit/results/<client>
```

Produces in `--outdir`: `<date>_report.md` (the combined report), `<date>_<check>.csv` per
check, and `<date>_audit.json` (counts). Omit `--pages`/`--sitemap` to skip checks 4/6.

**Thresholds** (all flags, tune per site): `--lhf-min-impr` (50), `--ctr-min-impr` (100),
`--ctr-factor` (0.6 of expected CTR), `--outdated-before` (2025 → flags years ≤ 2024),
`--cannib-min-impr` (10), `--bad-pattern` (no-index URL regex for check 4).

`--brand-regex` is applied to **all** query-based checks (cannibalization, low-hanging-fruit, CTR,
outdated), not just cannibalization — brand/navigational terms legitimately rank high and broad and
would crowd out real opportunities everywhere. **Include non-English / transliterated brand
variants** (e.g. a Latin name plus its Chinese name and common misspellings); an English-only
pattern lets those leak through and brand-dominate the results, e.g. `--brand-regex 'acme|阿克米|akmi|site:'`.

## Step 3 — Interpret & present

The report opens with an **Overview — key findings** section in point form: per check, the
count plus a few bullets that **name the important pages/issues** (e.g. the competing URLs for
cannibalization). Then a section per check with a one-line finding + a top-N table; full data is
in the CSVs.
Reading guide:
- **Cannibalization / Low-hanging fruit / CTR:** ranked by impact (severity / est. extra clicks /
  missed clicks). Act top-down.
- **Index hygiene:** pages matching admin/cart/etc. patterns that still get impressions → check
  for `noindex`/robots. Pattern-based, so eyeball for false positives.
- **Outdated:** old-year queries/URLs still drawing impressions → refresh or repoint.
- **Sitemap indexing:** missing = in sitemap but no GSC impressions (not-indexed **or** never
  shown). Confirm a sample via URL Inspection before acting.

Point the user at `<date>_report.md`. Record any per-client tuning (brand term, bad-pattern
additions, recurring issues) in `MEMORY.md`.
