---
name: gsc-audit(GSC)
description: Run a full Google Search Console audit — keyword cannibalization (pages competing for the same query / consolidate-canonicalize candidates), low-hanging-fruit (striking-distance) keywords, CTR opportunities, index hygiene (pages indexed but shouldn't be), outdated content, and sitemap indexing (submitted URLs with no impressions / not-indexed candidates) — in ONE combined report. Use for a full GSC checkup / health report, several GSC checks at once, OR any single one of these checks (cannibalization, striking-distance, CTR, index hygiene, outdated content, sitemap-vs-GSC) — run the audit and read the relevant section.
---

# GSC Audit (GSC)

Runs six GSC checks off shared pulls and writes **one** combined report (summary + top-N table
per check + a per-check CSV). This is the single GSC checking skill: it bundles its own
cannibalization and sitemap-indexing analyzers (`analyze_cannibalization.py`,
`sitemap_index_check.py`), so it is fully self-contained. For a **single** check, run the audit
and read that check's section/CSV (omit `--pages`/`--sitemap` to skip the page-based checks).

| # | Check | Data |
| --- | --- | --- |
| 1 | Keyword cannibalization | query×page |
| 2 | Low-hanging fruit (pos 4–20) | query×page |
| 3 | CTR opportunity (good pos, low CTR) | query×page |
| 4 | Index hygiene (indexed but shouldn't be) | page |
| 5 | Outdated content (old year still ranking) | query×page |
| 6 | Sitemap indexing (in sitemap, missing from GSC) | page + sitemap |

## When to use this skill

- "run a full GSC audit / checkup / health report", or several of the checks above at once
- **Keyword cannibalization** — pages/URLs competing for the same query, what to consolidate /
  canonicalize / redirect (check 1)
- **Striking-distance / low-hanging fruit** — queries at position 4–20 to push onto page 1 (check 2)
- **CTR opportunity** — good rank, low click-through, title/meta rewrites (check 3)
- **Index hygiene** — admin/cart/etc. URLs getting impressions that shouldn't be indexed (check 4)
- **Outdated content** — old-year queries/URLs still ranking (check 5)
- **Sitemap indexing** — sitemap URLs with no GSC impressions (not-indexed / zero-impression
  candidates) (check 6)

For any single one of these, still run this skill and read the matching section/CSV — there is no
longer a separate per-check skill.

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
`--cannib-min-impr` (10), `--bad-pattern` (no-index URL regex for check 4),
`--include-homepage` (off — homepage is dropped from checks 1–3, see below).

**Homepage is excluded from checks 1–3** (cannibalization, low-hanging-fruit, CTR) by default: it
ranks broadly for many queries, so it always shows keyword overlap and striking-distance rows while
its real CTR upside is limited. "Homepage" = the site root, locale roots (`/en/`, `/zh-hk/`), and
index files (`/index.html`, `/index.php`), detected via `--base` — so pass `--base` for this to
work. Each affected check keeps a one-line note in the report saying how many homepage rows were
hidden. Checks 4–6 (index hygiene, outdated, sitemap) still include the homepage. Pass
`--include-homepage` to keep it in all checks (e.g. a site whose homepage genuinely competes).

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
  missed clicks). Act top-down. Real cannibalization on these sites is usually a page vs a
  *near-copy* of itself — watch for a page vs its `/…-authenticity/` (or `/…/authenticity/`)
  variant, its language variant (`/en/…`, `…-en/`), Shopify singular-vs-plural collections
  (`/collections/x-band` vs `/collections/x-bands`), and overlapping `*-vs-*` comparison articles.
  Those are consolidate/canonicalize candidates, not distinct pages. (The analyzer strips
  `#anchor`/`?query-string` variants of the same page by default so they don't fake cannibalization.)
- **Index hygiene:** pages matching admin/cart/etc. patterns that still get impressions → check
  for `noindex`/robots. Pattern-based, so eyeball for false positives.
- **Outdated:** old-year queries/URLs still drawing impressions → refresh or repoint.
- **Sitemap indexing:** missing = in sitemap but no GSC impressions (not-indexed **or** never
  shown — the API only knows pages that *got impressions*, not true index status). Confirm a
  sample via URL Inspection before acting.

Point the user at `<date>_report.md`. Record any per-client tuning (brand term, bad-pattern
additions, recurring issues) in `MEMORY.md`.
