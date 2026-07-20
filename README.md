# Onsite Checking Workflow

A Claude Code workspace for onsite SEO checks. It bundles three data sources —
**Ahrefs** (off-page / keyword data), **Screaming Frog** (technical crawls), and
**GSC** (Google Search Console) — behind a single set of skills.

You don't run scripts by hand. Open this folder in Claude Code and **ask in plain
English** — Claude routes your request to the right skill, pulls the data, and writes
a cleaned summary into that skill's `results/` folder.

## Setup

- **Ahrefs** — connected via the claude.ai Ahrefs connector (no local setup).
- **Screaming Frog** — the SF MCP must be running locally (see `.mcp.json`); Claude
  crawls the site or reuses a recent crawl.
- **GSC** — copy `.env.example` → `.env`, add your OAuth client, and copy
  `gsc/clients.example.json` → `gsc/clients.json`. First run opens a browser to
  authorize each Google account. Details in `gsc/CLAUDE.md`.

## Skills — what to ask for

Ahrefs
- **keyword-research** — "find keywords for {topic} in {country}"; volume, KD, CPC, seed expansion.
- **competitor-analysis** — "who are my competitors for {domain}", keyword overlap, traffic gap.
- **site-audit** — "run an Ahrefs site audit" for a configured project; issues, health score.

Screaming Frog (crawl-based)
- **h1-check** — "check H1 issues on {site}"; missing, duplicate, or multiple H1s.
- **hreflang-analysis** — "audit hreflang on {site}"; x-default, locales, return links.

GSC
- **traffic-analysis** — "give me a weekly/monthly traffic update for {client}"; clicks/impressions/position deltas, target URL + keyword tracking, top movers.
- **gsc-audit** — "run a full GSC checkup for {client}", or any single check: keyword cannibalization ("which pages compete for the same query"), striking-distance, CTR, index hygiene, outdated content, sitemap indexing ("are {client}'s sitemap URLs indexed / getting impressions"). All in one report.

## How it's organized

- `CLAUDE.md` — router + full skills index (start here to understand routing).
- `.claude/skills/<name>/` — each skill: a `SKILL.md` plus its own analyzer script.
- `ahrefs/`, `screaming-frog/`, `gsc/` — per-family rules (their own `CLAUDE.md`) and
  the generated `data/` (raw) + `results/` (analysis) folders. These outputs are
  gitignored and regenerated on demand.
- `MEMORY.md` — running log of quirks and per-site exceptions found while working.
- `CREATING_A_SKILL.md` — guide + templates for adding a new skill.
