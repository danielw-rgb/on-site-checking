---
name: site-audit(Ahrefs)
description: Pull Ahrefs Site Audit data (issues, crawled pages, page-explorer reports) for a configured project, clean it, and write a Markdown summary. Use when the user asks for an Ahrefs site audit, site-health score, technical issues from Ahrefs (not Screaming Frog), keyword cannibalization, or audit-issue triage.
---

# Ahrefs Site Audit

Wraps the Ahrefs MCP `site-audit-*` tools into a raw → cleaned → summary pipeline. Family-wide rules (including the tool-name prefix) live in `ahrefs/CLAUDE.md`.

**Naming note:** this is the **Ahrefs** site audit. Technical crawls via Screaming Frog use the SF skills (`h1-check`, `hreflang-analysis`, …) and follow `screaming-frog/CLAUDE.md`. If the user just says "site audit", clarify which tool they want.

## When to use this skill

The user asks anything about:
- Ahrefs site audit, Ahrefs site-health score
- Ahrefs audit issues (broken links, redirect chains, etc. as Ahrefs sees them)
- crawled-pages report, page-explorer queries against an existing Ahrefs project
- keyword cannibalization (an existing Ahrefs site_audit task pattern)

## Step 1 — Gather required inputs

1. **`{project-name}`** — kebab-case slug, used as the per-project subfolder under `data/` and `results/`.
2. **Ahrefs project identifier** — Ahrefs Site Audit runs against a pre-configured project in the user's Ahrefs account. Ask for the project's identifier (name or ID as it appears in `management-projects`). If unknown, call the Ahrefs MCP `management-projects` tool to list available projects.
3. **What to extract** — the user's actual question (e.g. "show me the worst issues", "cannibalization across blog pages", "pages with 4xx"). This decides which `site-audit-*` tool to call.

## Step 2 — Fetch raw data via Ahrefs MCP

1. Call the Ahrefs MCP `doc` tool for any `site-audit-*` tool before its first use this session.
2. Common picks:
   - **Issue triage** → `site-audit-issues`
   - **Cannibalization / per-URL data** → `site-audit-page-explorer` (filter by what's needed)
   - **Page content / individual page inspection** → `site-audit-page-content`
3. Save the raw JSON:

   ```
   ahrefs/site-audit/data/{project-name}/{YYYY-MM-DD}.json
   ```

   If multiple tools were called, give each its own filename (append `_issues`, `_page-explorer`, etc. after the date). Same-day reruns append `_v2`, `_v3`, …
4. If the response includes `render_with`, call that render tool too. Raw JSON is still saved first.

## Step 3 — Clean

```bash
python ".claude/skills/site-audit(Ahrefs)/site_audit.py" \
  "ahrefs/site-audit/data/{project-name}/{YYYY-MM-DD}.json" \
  "ahrefs/site-audit/results/{project-name}/{YYYY-MM-DD}.json"
```

## Step 4 — Write the Markdown summary (and optional CSV)

```
ahrefs/site-audit/results/{project-name}/{YYYY-MM-DD}_summary.md
```

If the analysis produces a tabular finding (e.g. cannibalization pairs, per-URL issues), also write a CSV next to the `.md` with the same stem (e.g. `{YYYY-MM-DD}.csv` or `{YYYY-MM-DD}_cannibalization.csv`) in the same `results/{project-name}/` folder.

Summary contents:
- The Ahrefs project queried, what filter / view was used, raw and filtered row counts.
- Top issues or affected URLs grouped by severity.
- One clear next step (e.g. "redirect these 4 cannibalized URLs to /pricing").
