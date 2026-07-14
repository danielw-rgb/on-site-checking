# Ahrefs Family — Universal Rules

These rules apply to all Ahrefs-family skills (`keyword-research`, `competitor-analysis`, `site-audit`). Each skill's `SKILL.md` covers its own steps; this file covers what's shared.

Routing and the skills index live in the root `CLAUDE.md`.

## Folder layout (under `ahrefs/`)

One workspace folder per skill; inside it, raw pulls in `data/`, everything the skill
generates (cleaned JSON + Markdown summary + optional CSV) in `results/`, both keyed by a
per-project subfolder. The whole `ahrefs/<skill>/` tree is a **regenerable workspace** (gitignored) —
skills recreate the folders on demand.

```
keyword-research/
  input/                 # user-supplied seed keyword inputs (.csv or .txt)
  config/                # per-project filter rules: {project}.json
  data/{project}/        # raw JSON from Ahrefs MCP
  results/{project}/     # cleaned JSON + Markdown summary (+ optional CSV)
competitor-analysis/
  data/{project}/
  results/{project}/
site-audit/
  data/{project}/
  results/{project}/
```

Each skill's **cleaning script** — and, for keyword-research, the `filter_config/` template
(`README.md` + `_example.json`) — lives next to that skill's `SKILL.md` under
`.claude/skills/<skill>(Ahrefs)/`, **not** in the `ahrefs/` workspace. This keeps each skill a
self-contained, committed unit while its outputs stay in the local workspace.

## Pipeline shape (every Ahrefs skill follows this)

1. **Ask for `{project}`** — short kebab-case slug (e.g. `acme-q2`). Used as the per-project subfolder under the skill's `data/` and `results/`.
2. **Confirm task-specific inputs** — each skill enumerates these (e.g. keyword-research needs seed keywords + country). Don't call any Ahrefs tool until they're confirmed.
3. **Collect raw data via `mcp__claude_ai_Ahrefs__*`** — save the raw JSON exactly as returned to `ahrefs/<skill>/data/{project}/`. Monetary values are in USD cents; the cleaning script handles conversion.
4. **Run the skill's cleaning script** (`.claude/skills/<skill>(Ahrefs)/<script>.py`) — produces cleaned JSON in `ahrefs/<skill>/results/{project}/`. Filtered file is the source of truth for the summary.
5. **Write the user-facing summary** to `ahrefs/<skill>/results/{project}/{YYYY-MM-DD}_summary.md`. Answer the user's question; don't recap the data.

## Naming rules

The project is a **subfolder**; the filename is the `{YYYY-MM-DD}` date, shared across `data/`
and `results/` so a run's raw and cleaned files line up.

| Stage    | Path                                                        |
| -------- | ---------------------------------------------------------- |
| Raw      | `ahrefs/<skill>/data/{project}/{YYYY-MM-DD}.json`          |
| Filtered | `ahrefs/<skill>/results/{project}/{YYYY-MM-DD}.json`       |
| Summary  | `ahrefs/<skill>/results/{project}/{YYYY-MM-DD}_summary.md` |

- `<skill>` is the skill folder name (hyphenated): `keyword-research`, `competitor-analysis`, `site-audit`.
- Date is the creation date in the user's local time, `YYYY-MM-DD`.
- Same-day reruns for the same project + skill: append `_v2`, `_v3`, … to the date.
- Multiple tools in one run: append a descriptor after the date (e.g. `{YYYY-MM-DD}_top-pages.json`).
- Multi-market keyword research: append `_{country}` after the date (e.g. `2026-06-11_hk.json`).

## Keyword research filter routing

If `ahrefs/keyword-research/config/{project}.json` exists, the cleaning script applies it automatically (it derives `{project}` from the raw input's parent folder).

- **Numeric filters → API `where` clause at fetch time.** Covers `volume`, `global_volume`, `difficulty`, `cpc`, `traffic_potential`, `word_count`. Costs zero extra Ahrefs units. API `cpc` is in USD cents (`cpc > 500` means CPC > $5).
- **Intent filters → `filter_config` only.** `exclude_branded` (bool), `require_intents` (list — keep row if it has ANY), `exclude_intents` (list — drop row if it has ANY). Valid intents: `informational`, `navigational`, `commercial`, `transactional`, `branded`, `local`. The API can't express these cleanly because `intents` is a nested object.
- The config also accepts numeric keys (`min_volume`, `max_difficulty`, `min_cpc_usd` in USD, `max_traffic_potential`, etc.) — use them only when re-filtering an existing raw file without re-fetching.
- Never duplicate the same filter in both places.
- To change thresholds for a project: edit `ahrefs/keyword-research/config/{project}.json`. **Do not edit the script.**

(The config template `.claude/skills/keyword-research(Ahrefs)/filter_config/{README.md,_example.json}` is a human-facing reference — skip it when following this workflow.)

## Notes for the AI

- Always call `mcp__claude_ai_Ahrefs__doc` for an Ahrefs tool **before its first use in a session**.
- When an Ahrefs response includes `render_with` in its metadata, call the specified render tool — but still persist the raw JSON to `data/{project}/` first.
- Do not skip the cleaning step, even if the raw data looks small. The filtered file is the source of truth for the summary.
- The `{YYYY-MM-DD}_summary.md` in `results/{project}/` is the user-facing deliverable. Keep it short and answer the question asked, not everything the data contains.
