---
name: keyword-research(Ahrefs)
description: Pull Ahrefs Keywords Explorer data for a seed list in a chosen market, clean and filter the rows, and write a Markdown summary. Use when the user asks about keyword research, keyword volume/difficulty/CPC, seed keyword expansion, or any "find me keywords for X in country Y" task.
---

# Keyword Research (Ahrefs)

Wraps the Ahrefs MCP `keywords-explorer-*` tools into a reproducible raw → cleaned → summary pipeline. Family-wide rules (naming, MCP `doc` requirement, USD-cents handling, tool-name prefix) live in `ahrefs/CLAUDE.md` — read it once per session, then follow the steps below.

## When to use this skill

The user asks anything about:
- keyword research, finding keywords, seed expansion
- search volume, KD/difficulty, CPC, traffic potential
- "what keywords should we target for X"
- a keyword list scored against a specific market

## Step 1 — Gather required inputs (ask the user if missing)

Three inputs are mandatory before any Ahrefs call:

1. **`{project-name}`** — short kebab-case slug, used as the per-project subfolder under `data/` and `results/` (e.g. `acme-q2`). Ask if not provided.
2. **Seed keywords** — either typed in chat, or a file at `ahrefs/keyword-research/input/*.{csv,txt}` (one keyword per line, or one CSV column). If a file is used, record its filename for the summary.
3. **Country / region** — two-letter ISO 3166-1 alpha-2 code (`hk`, `us`, `gb`, `sg`, …). If the user names multiple markets, run the pipeline once per country and append the country code to each filename's date-stem (e.g. `2026-06-11_hk.json`).

Do not call any Ahrefs tool until all three are confirmed.

## Step 2 — Fetch raw data via Ahrefs MCP

1. Call the Ahrefs MCP `doc` tool for any keywords-explorer tool before its first use this session.
2. Call the appropriate tool (typically `keywords-explorer-overview`; use `matching-terms`, `related-terms`, or `search-suggestions` if the user asked for expansion). Pass the seed keywords and `country` parameter.
3. **Push numeric filters into the API `where` clause** when the user gave thresholds (`volume`, `global_volume`, `difficulty`, `cpc` in **USD cents**, `traffic_potential`, `word_count`). This costs zero extra Ahrefs units and avoids re-fetching.
4. Save the raw JSON exactly as returned (monetary values stay in USD cents; the cleaning script converts):

   ```
   ahrefs/keyword-research/data/{project-name}/{YYYY-MM-DD}.json
   ```

   Add `_{country}` after the date for multi-market runs (`{YYYY-MM-DD}_{country}.json`). If a same-day rerun would overwrite an existing file, append `_v2`, `_v3`, …

5. If the response includes `render_with` in its metadata, call that render tool too — but the raw JSON is still saved first.

## Step 3 — Clean and filter

Run the cleaning script with explicit input/output paths:

```bash
python ".claude/skills/keyword-research(Ahrefs)/keyword_research.py" \
  "ahrefs/keyword-research/data/{project-name}/{YYYY-MM-DD}.json" \
  "ahrefs/keyword-research/results/{project-name}/{YYYY-MM-DD}.json"
```

The script auto-applies `ahrefs/keyword-research/config/{project-name}.json` if it exists (it derives `{project-name}` from the input's parent folder). See `.claude/skills/keyword-research(Ahrefs)/filter_config/_example.json` for the config template.

**Filter placement rules:**
- **Numeric filters** belong in the API `where` clause (step 2). Use the filter_config's numeric keys (`min_volume`, `max_difficulty`, `min_cpc_usd` in USD, etc.) **only** when re-filtering an existing raw file without re-fetching.
- **Intent filters** (`exclude_branded`, `require_intents`, `exclude_intents`) live in filter_config only — the API can't express them cleanly. Valid intents: `informational`, `navigational`, `commercial`, `transactional`, `branded`, `local`.
- Never duplicate the same filter in both places.

To change thresholds for a project, edit `ahrefs/keyword-research/config/{project-name}.json`. **Do not edit the script.**

## Step 4 — Write the Markdown summary

Read the filtered JSON and write a short summary that **answers the user's question** — key findings, notable numbers, suggested next step. Keep it tight; the filtered file is the source of truth, not the summary.

```
ahrefs/keyword-research/results/{project-name}/{YYYY-MM-DD}_summary.md
```

Include:
- The seed list (or filename if uploaded), country, raw and filtered row counts, and the filter config path if one applied.
- 5–10 top opportunities by volume × intent fit, with KD and CPC.
- Anything anomalous (e.g. all rows have zero local volume — likely wrong country code).
