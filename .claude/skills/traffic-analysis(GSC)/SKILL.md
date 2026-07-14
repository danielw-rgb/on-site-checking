---
name: traffic-analysis(GSC)
description: Summarise Google Search Console organic traffic for a client and draft a client-ready weekly + monthly update in three layers — overall site traffic, per target-URL traffic, and per target-keyword rankings — plus top movers. Target URLs and keywords are kept in a per-client watchlist file and reused every run. Use when the user asks for a weekly/monthly traffic report, an organic-traffic summary, "how did traffic change", performance week-over-week or month-over-month, or a client update on GSC rankings for specific pages/keywords.
---

# Traffic Analysis (GSC)

Pulls GSC Search Analytics and produces the numbers for a **client-facing weekly + monthly
update**, in **three layers**:

1. **Overall** — whole-site traffic (from the `date` pull; includes anonymized queries).
2. **Target URLs** — per-page traffic for a saved watchlist (from the `page,date` pull).
3. **Target keywords** — per-query position/traffic for a saved watchlist (from `query,date`).

| Comparison | Current window | Baseline |
| --- | --- | --- |
| **Weekly** | last 7 days | the 7 days before |
| **Monthly** | last 28 days (`--month-mode 28d`, default) | the previous 28 days — or use `calendar` for current month-to-date vs the same days last month |

Both windows end at `asof` = the latest date present in the data (GSC lags ~2–3 days).

## When to use this skill

- "give me the weekly / monthly traffic update for <client>"
- "how did organic traffic change this week / this month"
- "how are our target pages / target keywords doing"
- a recurring client update on organic traffic + target-URL / target-keyword performance

For cannibalization, striking-distance, or a full health audit, use the other `(GSC)` skills.

## The per-client watchlist (target URLs + keywords)

Each client's target URLs and target keywords live in a JSON file next to this skill:

```
.claude/skills/traffic-analysis(GSC)/targets/<client>.json
```

```json
{
  "client": "<client>", "property": "<property>", "account": "<slug>",
  "target_urls": ["https://.../page-a/", "https://.../page-b/"],
  "target_keywords": ["keyword one", "keyword two"]
}
```

The analyzer reads it via `--targets-file`. When the user hands over a list, **save/update this
file first** (dedupe entries), then every run reuses it. `--target-keywords "a,b"` can add ad-hoc
terms on top. URL matching normalizes trailing slash, `#fragment`, `?query`, and case.

## Step 0 — Bootstrap the shared workspace (first run in a project)

This skill is self-contained: it ships its own copy of the GSC connector + templates in
`_shared/`. On the **first** GSC skill you run in a project, materialise the shared workspace:

```bash
python3 ".claude/skills/traffic-analysis(GSC)/_shared/bootstrap.py"
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
   (if the token is missing, the connector prints the exact `auth` command — relay it).

Check `MEMORY.md` for this client's property/account, brand term, and any watchlist notes (if
present). **This machine uses `python3` (there is no `python`).** Fuller family rules live in
`gsc/CLAUDE.md` if present.

## Step 1 — Gather inputs (ask only what's missing)

1. **Account slug** + **property**, or a **`--client <slug>`** from `gsc/clients.json`.
2. **Watchlist** — the `targets/<client>.json` file. If it doesn't exist, ask the user for the
   target URL list + target keyword list and create it (dedupe). If it exists, reuse it.
3. **`asof` (optional)** — defaults to the latest date in the pull; pass `--asof` to pin a report date.
4. **Ad-hoc focus (optional)** — `--query-filter` / `--page-filter` narrows only the *overall*
   layer to a topic; the target layers are unaffected.

## Step 2 — Pull the data via the connector

Reach back **≥ 56 days** (the previous 28-day window) so both comparisons are covered. For a report
as of ~`today − 3 days`, use `--date-from <asof − 55 days>` and `--date-to <latest-available>`.
(For `--month-mode calendar`, reach back to the 1st of the previous month instead.)

The **`page,date` pull is required** whenever the watchlist has target URLs (layer 2); the
`date` and `query,date` pulls are always needed.

```bash
# (1) site totals + trend — dimensions `date` (includes anonymized-query traffic)
python3 gsc/connector/gsc_fetch.py query \
  --account <slug> --property <property> \
  --dimensions date --date-from <asof-55d> --date-to <asof> \
  --output gsc/traffic-analysis/data/<client>/<YYYY-MM-DD>_date.ndjson

# (2) keyword level — dimensions `query,date` (target keywords + query movers)
python3 gsc/connector/gsc_fetch.py query \
  --account <slug> --property <property> \
  --dimensions query,date --date-from <asof-55d> --date-to <asof> \
  --output gsc/traffic-analysis/data/<client>/<YYYY-MM-DD>_query-date.ndjson

# (3) page level — dimensions `page,date` (target URLs + page movers) — REQUIRED for target URLs
python3 gsc/connector/gsc_fetch.py query \
  --account <slug> --property <property> \
  --dimensions page,date --date-from <asof-55d> --date-to <asof> \
  --output gsc/traffic-analysis/data/<client>/<YYYY-MM-DD>_page-date.ndjson
```

(or `--client <slug>` in place of `--account` + `--property`.) `<client>` is the short slug used
as the subfolder under `data/` and `results/`. Same-day reruns append `_v2` to the date filename.

## Step 3 — Run the analyzer

```bash
python3 ".claude/skills/traffic-analysis(GSC)/analyze_traffic.py" \
  --date-file    gsc/traffic-analysis/data/<client>/<YYYY-MM-DD>_date.ndjson \
  --query-file   gsc/traffic-analysis/data/<client>/<YYYY-MM-DD>_query-date.ndjson \
  --page-file    gsc/traffic-analysis/data/<client>/<YYYY-MM-DD>_page-date.ndjson \
  --targets-file ".claude/skills/traffic-analysis(GSC)/targets/<client>.json" \
  --output       gsc/traffic-analysis/results/<client>/<YYYY-MM-DD>.json \
  --property <property> --client <client>
```

Optional flags:
- `--month-mode calendar` — current month-to-date vs the same days last month (default rolling `28d`).
- `--target-keywords "a,b"` — extra ad-hoc queries on top of the watchlist.
- `--query-filter '<regex>'` / `--page-filter '<regex>'` — narrow the **overall** layer to a topic.
- `--asof <YYYY-MM-DD>` — pin the report end date. `--top <N>` — movers per direction (default 10).

Writes the JSON report, `_windows.csv`, `_target-urls.csv`, `_target-keywords.csv`,
`_movers-query.csv` (and `_movers-page.csv`), plus a stdout summary.

## Step 4 — Read the output

Top-level JSON keys:

| Key | Meaning |
| --- | --- |
| `meta` | property, `asof`, month mode, focus, watchlist counts, and the lag/weighting note. |
| `overall` | `weekly` + `monthly`, each with `current`/`previous` window metrics + a `delta`. |
| `target_urls` | per URL: `weekly`/`monthly` (`current`/`previous` metrics, `clicks_delta`, `position_movement`), `latest` day, and `found` (false = no GSC impressions in the whole pull → likely not indexed). |
| `target_keywords` | per query: same shape plus `first_page` (position ≤ 10). |
| `movers` | top query and page gainers/losers by click delta between the monthly windows. |

Deltas: `clicks`/`impressions` carry `abs` + `pct`; `ctr` carries `abs_points`; `position` carries
`abs` + `improved` (a **lower** number is better). `position_movement` is positive when a target
improved. A target URL/keyword with `found: false` (or a null `current`) got **no impressions** —
call that out (unindexed / no visibility), don't report it as a zero.

## Step 5 — Write the client update

Draft `gsc/traffic-analysis/results/<client>/<YYYY-MM-DD>_summary.md` in a short, plain voice,
structured by the three layers (see the firstpage-hk summary as the model). Use this template —
**summary-at-top** (reader gets the quick read first, detail below), a label-then-blank-line rhythm
for the weekly/monthly blocks, and each target keyword carries **both** its 7-day and 28-day
position move:

```
# <property> — organic traffic & SEO update (as of <asof>)

Source: Google Search Console · property <property> · account <slug>

Watchlist: <N> target URLs + <M> target keywords. GSC lags ~2–3 days, so this is as of <asof>.

## Summary

- <2–4 short action-oriented bullets — the whole story in one glance>.

Detail below.

## Overall traffic

Weekly (vs the previous 7 days):

<clicks ±pct (a → b), impressions ±pct, average position improved/eased from X to Y.>

Monthly (last 28 days vs the 28 before):

<the notable moves, plus a one-line "reads as X" interpretation if useful>.

## Target pages

- <page> — <the insight> (clicks/impressions, position, trend).

<Lead-in line for any not-indexed group>:

- <page(s) with no impressions over the pull → likely not indexed; recommend URL-Inspection>

(The other watched pages had little movement this period.)

## Target keywords

(Position change: "improved" = ranking got better / position number dropped; "slipped" = worse.)

Page 1 Target Keywords:

- <keyword> (position <P>, improved/slipped <a> in 7 days, improved/slipped <b> in 28 days)

Climbing toward page 1:

- <keyword> (position <P>, improved/slipped <a> in 7 days, improved/slipped <b> in 28 days)

Slipping / needs work:

- <keyword> (position <P>, improved/slipped <a> in 7 days, improved/slipped <b> in 28 days)

Not ranking (no GSC impressions):

- <keyword>

<one line on why these bare terms aren't surfacing yet>

Data: <YYYY-MM-DD>.json (+ the _*.csv files) in this folder.
```

Per-keyword change values: 7-day move = `weekly.position_movement`; 28-day move =
`monthly.previous.position − monthly.current.position` (positive = improved, since a lower position
number is better). Group keywords by `first_page` (page 1) vs off-page, then by direction. If a
keyword has no prior-period data (`weekly`/`monthly` `previous` is null), write "no prior-period
data to compare" rather than a fabricated number; write "roughly flat" for a move near 0.

Formatting rules (the user's readability preferences):
- **Summary first.** Put the takeaways in a `## Summary` block right under the header so the reader
  gets the quick read up front, then "Detail below." and the full breakdown. Don't repeat the
  takeaways again at the bottom.
- **Breathe with spacing.** For the weekly/monthly blocks, put the label (`Weekly (vs the previous
  7 days):`) on its own line, then a blank line, then the sentence. Group target keywords under
  labelled sub-headers (Page 1 / Climbing / Slipping / Not ranking), one keyword per bullet line.
- **Write for a human reader, not a data dump.** Plain sentences and simple bullet lists.
- **No inline markdown emphasis on routine labels/numbers** — write `weekly` and `+32%` as plain
  text, not `**weekly**` / `**+32%**`. Bold is fine, but only for a genuine callout (e.g. a page
  that isn't indexed) — use it sparingly.
- **No markdown tables** (`|`) — they're hard to read in plain text. Use bullets or prose.
- **Only mention target URLs / keywords that have an insight** — a move, a page-1 entry, a
  problem. Don't list every watchlist item one by one; a short "(others had little movement)" is enough.
- **Only report what GSC supports.** No leads/conversions (HubSpot) or Ahrefs "AI visibility" —
  omit, don't invent.
- Flag any `found: false` target URL as a likely indexing issue. Point at the JSON + CSVs for detail.
- Record durable facts (watchlist changes, property/account, recurring issues) in `MEMORY.md`.

## Notes & limits

- **`query,date` / `page,date` drop anonymized/rare queries**, so the target layers can read lower
  than the overall (`date`) totals. The overall headline is complete.
- **"Today" isn't available** — GSC lags ~2–3 days; `latest` is the most recent day in the pull.
- Default monthly is a rolling **28d vs previous 28d** (stable, full-vs-full). Use
  `--month-mode calendar` if a client wants named-month figures.
