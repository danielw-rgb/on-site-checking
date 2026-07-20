# GSC family — universal rules

Google Search Console data for the Onsite Checking Workflow. GSC is reached **directly**
via the Search Console API (not through Ahrefs). A shared connector handles auth + data
pulls; each `(GSC)` skill layers analysis on top. This file is auto-loaded when working under
`gsc/`. Read it once per session before running any `(GSC)` skill.

## Auth model — OAuth, multi-account

We are an agency: clients grant access to our agency Google logins (`agency1@gmail.com`,
`agency2@gmail.com`, …), each holding 20+ client properties. We are **not** property owners,
so a service account (which an owner must add) is not viable. We use **OAuth installed-app**:

- **One** OAuth "Desktop app" client (one `client_id`/`secret`, stored in repo-root `.env`)
  works for **all** agency Google accounts. The account that *consents* determines which
  properties are visible.
- Consent **once per agency Google account**; the refresh token is cached at
  `gsc/credentials/token_<account>.json`. No browser login on subsequent runs.
- Per client, choose the **account slug** (the Gmail that has access) + the **property**.

⚠️ **Refresh-token expiry gotcha:** set the OAuth consent screen to **"Production"**
(External + Production; click through the "unverified app" warning). If left in **"Testing"**,
refresh tokens expire after **7 days** and every account must re-auth weekly.

## Setup (one-time)

1. `pip install -r gsc/requirements.txt`
2. Google Cloud Console → enable **Google Search Console API** → create an OAuth **Desktop app**
   client → set consent screen to **Production**.
3. Put `GSC_OAUTH_CLIENT_ID` + `GSC_OAUTH_CLIENT_SECRET` in `.env` (template: `.env.example`).
4. For each agency Google login: `python gsc/connector/gsc_fetch.py auth --account <slug>`

## The connector — `gsc/connector/gsc_fetch.py`

Shared infrastructure. Every `(GSC)` skill calls it to fetch data; skills never talk to the API
directly.

```bash
# one-time consent per agency Google account
python gsc/connector/gsc_fetch.py auth --account agency1

# pull Search Analytics rows (paginates automatically, 25k rows/request)
python gsc/connector/gsc_fetch.py query \
  --account agency1 --property sc-domain:example.com \
  --dimensions query,page --date-from 2026-03-01 --date-to 2026-05-31 \
  --output gsc/<skill>/data/<client>/<YYYY-MM-DD>.ndjson
```

- **Dimensions:** `query,page` for keyword-level checks (drops anonymized queries); `page`
  alone for the complete indexed/performing-page list (index hygiene, sitemap cross-check).
- **Property formats:** `sc-domain:example.com` (Domain property) or `https://www.example.com/`
  (URL-prefix property, exact match incl. trailing slash).
- **Client registry (optional):** copy `gsc/clients.example.json` → `gsc/clients.json`
  (gitignored), map `slug → {account, property}`, then use `--client <slug>` instead of
  `--account` + `--property`.
- Output is **NDJSON**, one row per dimension combination, fields: the dimensions plus
  `clicks`, `impressions`, `ctr`, `position`. GSC data lags ~2–3 days; pick `--date-to`
  accordingly.

## Conventions

- **Output layout:** each GSC skill owns a workspace folder `gsc/<skill>/`, split into `data/`
  (raw) and `results/` (analysis), each keyed by a per-client subfolder:
  - raw pulls → `gsc/<skill>/data/<client>/<YYYY-MM-DD>.ndjson`
  - analysis + summary → `gsc/<skill>/results/<client>/<YYYY-MM-DD>.{json,csv}` and
    `<YYYY-MM-DD>_summary.md`
  - `<skill>` = the GSC skill folder name (e.g. `gsc-audit`, `traffic-analysis`);
    `<client>` = short client slug (e.g. `bandletic`). The date is the
    filename inside the folder; same-day reruns append `_v2`, `_v3` (e.g. `2026-06-30_v2.ndjson`).
    The property is recorded inside the summary, so one client folder can hold multiple properties.
- **Raw pulls** live under `gsc/<skill>/data/`; **analysis + summaries** under `gsc/<skill>/results/`.
  Both are gitignored (client data), regenerated on demand.
- **Credentials never commit:** `.env`, `gsc/credentials/*`, and `gsc/clients.json` are
  gitignored. Only `.env.example` and `gsc/clients.example.json` are tracked.

## Adding a new GSC skill

Each `(GSC)` skill drives its own connector call(s) inside its steps — no `requires:` block
(that's Screaming-Frog-only). Pattern: gather inputs (account/property/dates) → run the
connector to NDJSON in `gsc/<skill>/data/` → run the skill's analyzer → write a summary to
`gsc/<skill>/results/`. See `.claude/skills/keyword-cannibalization(GSC)/SKILL.md` as the reference.
