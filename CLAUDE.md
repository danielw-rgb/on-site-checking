# Onsite Checking Workflow

A unified workspace for onsite SEO checks. Tool families — **Ahrefs** (off-page data, keyword/competitor/site-audit), **Screaming Frog** (technical crawl-based audits), and **GSC** (Google Search Console performance data, via a direct OAuth connector) — share a single `.claude/skills/` index. Each user request maps to exactly one skill.

## Folder map

```
.
├── CLAUDE.md                          ← this file (router + skills index)
├── MEMORY.md                          ← running log of items / special requirements (PERSONAL — gitignored)
├── MEMORY.example.md                  ← tracked scaffold; copy to MEMORY.md on first use
├── CREATING_A_SKILL.md                ← guide + copy-paste templates for adding a new skill
├── .env / .env.example                ← local secrets (GSC OAuth client) — .env is gitignored
├── .mcp.json                          ← MCP servers: Screaming Frog + Ahrefs (Ahrefs over OAuth; set its url per host)
├── .claude/
│   ├── settings.local.json
│   └── skills/                        ← each skill = SKILL.md + its own scripts (self-contained)
│       ├── keyword-research(Ahrefs)/  ← SKILL.md · keyword_research.py · filter_config/ template
│       ├── competitor-analysis(Ahrefs)/  ← SKILL.md · competitor_analysis.py
│       ├── site-audit(Ahrefs)/        ← SKILL.md · site_audit.py
│       ├── h1-check(SF)/ · hreflang-analysis(SF)/    ← SKILL.md · analyzer .js
│       └── {gsc-audit,traffic-analysis}(GSC)/  ← SKILL.md · analyzer .py (gsc-audit bundles all checks)
├── ahrefs/
│   ├── CLAUDE.md                      ← Ahrefs family universal rules
│   ├── AHREFS_AGENT.md                ← standalone Ahrefs-agent brief for OTHER platforms (export only; not auto-loaded / no effect on this repo)
│   └── <skill>/{data,results}/        ← per-skill workspace: raw pulls + cleaned + summaries (gitignored)
└── screaming-frog/
    ├── CLAUDE.md                      ← SF family universal workflow
    ├── SF_AGENT.md                    ← standalone SF-agent brief for OTHER platforms (export only; not auto-loaded / no effect on this repo)
    ├── crawl_default.seospiderconfig  ← binary base config (don't edit by hand)
    ├── CRAWL_DEFAULTS.md
    ├── scripts/profile.js             ← optional per-site crawl-profile helper (not required)
    └── profiles/                      ← optional per-site crawl profiles (gitignored)
        # SF skills are stateless: crawl lives in the SEO Spider app; exports go to the
        # MCP's own base dir (not the repo); findings are returned in chat. No crawls/ or reports/.
└── gsc/
    ├── CLAUDE.md                      ← GSC family universal rules (OAuth multi-account)
    ├── GSC_AGENT.md                   ← standalone GSC-agent brief for OTHER platforms (export only; not auto-loaded / no effect on this repo)
    ├── connector/gsc_fetch.py        ← reusable auth + Search Analytics fetch → NDJSON
    ├── credentials/                  ← OAuth client secret + per-account tokens (gitignored)
    ├── clients.json                  ← slug → {account, property} registry (gitignored; .example tracked)
    └── <skill>/{data,results}/<client>/  ← raw NDJSON + analysis JSON/CSV/summaries, per skill+client (gitignored)
```

Sub-folder `CLAUDE.md`s under `ahrefs/` and `screaming-frog/` are auto-loaded by Claude Code when working in their subtree. Family-specific rules stay close to that family's data.

## Routing

1. **Match user intent to one skill** in the index below. The `available-skills` system reminder at session start lists their names and descriptions — that's the routing table. **Every skill name ends with a `(...)` tag listing every tool it uses**, pipe-separated (`(SF)`, `(Ahrefs)`, `(SF|Ahrefs)`, `(SF|Ahrefs|GSC)`, …). Scan the tag to see which MCPs / data sources a skill will touch.
2. **If the skill's tag contains `SF`**, **first** run the universal workflow in `screaming-frog/CLAUDE.md` (get URL → crawl or reuse a loaded crawl → wait until not busy → export to the SF base dir → analyze → findings in chat) for the SF parts. SF skills are stateless — nothing is written to the repo. Skip this step if `SF` is not in the tag.
3. **If the skill's tag contains `Ahrefs`**, read `ahrefs/CLAUDE.md` once per session for the naming + MCP `doc` rules, then follow the skill's steps for the Ahrefs parts.
4. **If the skill's tag contains `GSC`**, read `gsc/CLAUDE.md` once per session for the OAuth multi-account + property + naming rules, then run `gsc/connector/gsc_fetch.py` (auth once per agency account if no token yet) before the skill's analysis.
5. **For multi-tool skills** (e.g. `(SF|Ahrefs)`), apply each per-tool family rule above, then follow the skill's own steps which choreograph the cross-tool logic.
6. **If no skill fits**, do a one-off analysis and propose adding it as a new skill afterward.

## Repo memory & skill creation

- **`MEMORY.md` (read at the start of every run).** A running log of items, quirks, and special
  requirements found while using this repo — general rules, per-site exceptions, and per-skill
  notes. **It is personal and gitignored** (it holds client-confidential notes — agency accounts,
  properties, findings), so a fresh clone won't have one. **If `MEMORY.md` is missing, create it by
  copying `MEMORY.example.md`** (the tracked scaffold) and start logging — don't block the run.
  **Before running a skill, check `MEMORY.md`** for any entry under that skill or the target
  site, and apply it. **When you discover something worth remembering** during a check (a
  client-specific rule, a recurring gotcha, a per-site exception), add a one-line dated bullet under
  the right section: `- [YYYY-MM-DD] <site or scope> — <fact>. Why: <reason>.` Keep confidential
  detail here (never in a tracked file); skill outputs must not depend on it existing.
- **`CREATING_A_SKILL.md` (read before adding a skill).** Step-by-step guide + copy-paste `SKILL.md`
  templates for both families. When the user asks to add a skill, follow it instead of scanning the
  existing skills. It expands the "Adding a new skill" section below; that section stays the source
  of truth if the two ever disagree.

## Skills index

| Skill | What it does |
| --- | --- |
| `keyword-research(Ahrefs)` | Pull Ahrefs Keywords Explorer for seed list + market, clean, summarize. |
| `competitor-analysis(Ahrefs)` | Pull Ahrefs Site Explorer competitor data for a domain, clean, summarize. |
| `site-audit(Ahrefs)` | Pull Ahrefs Site Audit (issues / page-explorer / cannibalization), clean, summarize. |
| `h1-check(SF)` | Audit H1 tags from a Screaming Frog crawl — missing, duplicate, multiple. |
| `hreflang-analysis(SF)` | Audit hreflang annotations from a Screaming Frog crawl — x-default, locales, return links. |
| `gsc-audit(GSC)` | Full GSC checkup in one report — keyword cannibalization, low-hanging-fruit, CTR opportunity, index hygiene, outdated content, sitemap indexing. Also the home for any single one of these checks (bundles its own cannibalization + sitemap analyzers). |
| `traffic-analysis(GSC)` | Summarise GSC organic traffic (whole site or a topic/keyword/page focus) into a client-ready weekly + monthly update — clicks/impressions/CTR/position deltas, target-keyword rankings, top movers. |

All skills live at `.claude/skills/<name>/SKILL.md`. Supporting scripts (analyzers, helpers) live next to the SKILL.md.

## Conventions (quick reference)

- **Per-skill workspace:** each skill's generated output lives under its tool workspace in a per-skill folder, split `data/` (raw) + `results/` (analysis), keyed by a per-client/project subfolder. These trees are gitignored and regenerated on demand. **Exception — Screaming Frog** writes nothing to the repo (stateless): the crawl lives in the SEO Spider app and exports go to the MCP's own base dir.
- **Ahrefs layout:** `ahrefs/<skill>/data/{project}/{YYYY-MM-DD}.json` (raw) and `ahrefs/<skill>/results/{project}/{YYYY-MM-DD}.json` + `{YYYY-MM-DD}_summary.md`. Full rules → `ahrefs/CLAUDE.md`.
- **GSC output layout:** `gsc/<skill>/data/<client>/<YYYY-MM-DD>.ndjson` (raw) and `gsc/<skill>/results/<client>/<YYYY-MM-DD>.{json,csv}` + `_summary.md`. Auth is OAuth, one consent per agency Google account; credentials live in `.env` + `gsc/credentials/` (gitignored). Full rules → `gsc/CLAUDE.md`.
- **Screaming Frog is stateless:** connect to the SF MCP → crawl or reuse a loaded crawl → wait until not busy → export to the MCP's base dir (not the repo) → analyze → findings in chat. No crawl/report files are persisted. Full rules → `screaming-frog/CLAUDE.md`.
- **Same-day reruns** for the same project + skill: append `_v2`, `_v3` to keep prior outputs intact.
- **Monetary values from Ahrefs** are in USD cents. The Ahrefs cleaning scripts convert; downstream code (and you) should not.
- **Before first use of any Ahrefs MCP tool in a session**, call the Ahrefs MCP `doc` tool for it. Ahrefs tools are referenced by bare name (the host's server prefix varies); see `ahrefs/CLAUDE.md` → "MCP access".
- **`screaming-frog/crawl_default.seospiderconfig` is binary and managed by Screaming Frog.** Re-export from the SF UI to change settings — never edit by hand.

## Adding a new skill

**Principle: build each skill as a self-contained unit.** Skills are independent — they share routing and folder conventions, but their logic does not call into each other. When the user asks to add a new skill, scope your exploration to (a) this file, (b) the relevant family's `CLAUDE.md` (`ahrefs/` or `screaming-frog/`), and (c) one existing skill in the same family as a style reference. Do **not** read every skill in `.claude/skills/`. The only exception is when the user explicitly says the new skill should reuse or compose with another skill — in that case, read just the skills named.

1. Create `.claude/skills/<new-skill>(<Tools>)/SKILL.md` with `name:` and `description:` frontmatter. **Always end the skill name with a `(...)` tag listing every tool the skill uses, pipe-separated** — `(SF)`, `(Ahrefs)`, `(GSC)`, or combos like `(SF|Ahrefs)` or `(SF|Ahrefs|GSC)` for skills that touch more than one tool. This makes the tool surface readable at a glance from the `available-skills` reminder. The `name:` in frontmatter must match the folder name exactly. The `description:` is what triggers routing — be specific about when to use it.
2. Drop supporting scripts (analyzers, parsers) next to `SKILL.md` in the same folder.
3. Add a row to the **Skills index** above.
4. If the new skill belongs to the Screaming Frog family, no `requires:` block — it's stateless. In its steps: run the shared crawl workflow (`screaming-frog/CLAUDE.md`), export the element(s) it needs to the SF base dir via `sf_export_seo_element_urls` (`filter_name: "All"`), run its Node analyzer against that file (analyzer prints findings to stdout, writes no files), and report in chat. See `.claude/skills/h1-check(SF)/SKILL.md` as the reference.
5. If the new skill belongs to the Ahrefs family, no `requires:` block — each Ahrefs skill drives its own MCP calls inside its steps.
