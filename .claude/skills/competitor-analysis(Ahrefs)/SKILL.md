---
name: competitor-analysis(Ahrefs)
description: Pull Ahrefs Site Explorer competitor data for a target domain, clean the rows, and write a Markdown summary. Use when the user asks "who are my competitors", "compare us against X", competitor keyword overlap, organic-traffic gap analysis, or Site Explorer competitor reports.
---

# Competitor Analysis (Ahrefs)

Wraps the Ahrefs MCP `site-explorer-organic-competitors` tool (and related Site Explorer tools) into a raw → cleaned → summary pipeline. Family-wide rules (including the tool-name prefix) live in `ahrefs/CLAUDE.md`.

## When to use this skill

The user asks anything about:
- competitors of a domain, who else ranks for the same keywords
- competitor keyword overlap, content gap, organic-share comparison
- benchmarking traffic / referring domains against rivals
- competitor backlink or pages comparison

## Step 1 — Gather required inputs

1. **`{project-name}`** — kebab-case slug, used as the per-project subfolder under `data/` and `results/`.
2. **Target domain** — the site whose competitors we want (e.g. `firstpage.com.hk`). Confirm protocol/subdomain assumption with the user if ambiguous.
3. **Country / region** (optional) — pass as ISO 3166-1 alpha-2 if the user wants market-specific competitors. Otherwise omit.

If `{project-name}` or the target domain is missing, ask before calling any Ahrefs tool.

## Step 2 — Fetch raw data via Ahrefs MCP

1. Call the Ahrefs MCP `doc` tool for any Site Explorer tool before its first use this session.
2. Default tool: `site-explorer-organic-competitors`. If the user wants deeper context (top pages, traffic-by-country, referring domains), call the matching `site-explorer-*` tools and stitch them — save each as a separate raw file.
3. Save the raw JSON:

   ```
   ahrefs/competitor-analysis/data/{project-name}/{YYYY-MM-DD}.json
   ```

   If you ran multiple Site Explorer tools, give each its own filename (e.g. append `_top-pages`, `_refdomains`) after the date. Same-day reruns append `_v2`, `_v3`, …
4. If the response includes `render_with`, call that render tool too. Raw JSON is still saved first.

## Step 3 — Clean

Run the cleaning script with explicit paths:

```bash
python ".claude/skills/competitor-analysis(Ahrefs)/competitor_analysis.py" \
  "ahrefs/competitor-analysis/data/{project-name}/{YYYY-MM-DD}.json" \
  "ahrefs/competitor-analysis/results/{project-name}/{YYYY-MM-DD}.json"
```

The script handles USD-cents → dollars conversion and keeps only the fields needed downstream.

## Step 4 — Write the Markdown summary

```
ahrefs/competitor-analysis/results/{project-name}/{YYYY-MM-DD}_summary.md
```

Answer the user's question directly. Useful elements to include:
- Top N competitors with their organic traffic, shared keywords count, and overlap %.
- Stand-out gaps: keywords competitors rank for that the target doesn't.
- One-line strategic takeaway, not a recap of every row.
