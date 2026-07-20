# Creating a New Skill

Step-by-step guide + copy-paste templates for adding a skill to this repo, so you don't
have to scan every existing skill to learn the pattern. This expands the **"Adding a new skill"**
section of the root `CLAUDE.md` — read that section too; it is the source of truth if the two
ever disagree.

> **Scope rule (from CLAUDE.md):** build each skill as a **self-contained unit**. When adding one,
> only read (a) the root `CLAUDE.md`, (b) the relevant family's `CLAUDE.md` (`ahrefs/` or
> `screaming-frog/`), and (c) **one** existing skill in the same family as a style reference.
> Do NOT read every skill. Exception: the user explicitly says the new skill should reuse/compose
> with another named skill.

---

## Decide first

1. **Which tool family?** Off-page / keyword / competitor / Ahrefs-audit data → **Ahrefs**.
   Crawl-based technical audit → **Screaming Frog (SF)**. Touches both → multi-tool.
2. **Name + tag.** Folder name = `name:` frontmatter = exactly the same string, ending in a
   `(...)` tool tag: `(SF)`, `(Ahrefs)`, `(GSC)`, or a pipe combo like `(SF|Ahrefs)`.
   Use kebab-case for the descriptive part: `image-alt-check(SF)`.
3. **Description.** This is the routing trigger — be specific about *when* to use it and list the
   phrases a user would type. Vague descriptions cause mis-routing.

## Checklist (mirrors CLAUDE.md)

- [ ] Create `.claude/skills/<new-skill>(<Tools>)/SKILL.md` with `name:` + `description:` frontmatter.
- [ ] `name:` matches the folder name **exactly** (including the `(...)` tag).
- [ ] Drop any supporting scripts (analyzers, parsers, cleaning scripts) **next to** `SKILL.md` in the same folder — including Ahrefs cleaning scripts (they live in the skill folder, not `ahrefs/`).
- [ ] Add a row to the **Skills index** table in the root `CLAUDE.md`.
- [ ] Add a sub-section for the skill in `MEMORY.md` (under the right family).
- [ ] **SF skills:** no `requires:` block — stateless. The steps run the shared crawl workflow, export to the SF base dir, and analyze in chat (see template).
- [ ] **Ahrefs skills:** no `requires:` block — each skill drives its own MCP calls in its steps.
- [ ] Verify routing: the `description` should make it obvious which user requests map here and
      not collide with an existing skill.

---

## Template A — Screaming Frog skill `(SF)`

Copy into `.claude/skills/<name>(SF)/SKILL.md`. Replace every `<…>`. SF skills are **stateless**:
no `requires:` block, and they write nothing to the repo — the crawl lives in the SEO Spider app,
the export goes to the MCP's own base dir, and findings are returned in chat.

```markdown
---
name: <name>(SF)
description: <one sentence on what it audits>. Use when the user asks about <phrase>, <phrase>, <phrase>.
---

# <Skill Title>

<One-paragraph summary of what it flags and from which crawl data.> Stateless — drives the SF MCP
and reads the crawl result directly; writes nothing to the repo. Shared crawl mechanics live in
`screaming-frog/CLAUDE.md`.

## When to use this skill
The user asks anything about:
- <trigger phrase>
- <trigger phrase>

## Step 1 — Get a crawl (per `screaming-frog/CLAUDE.md`)
Get `SITE_URL`, then reuse a loaded crawl (`sf_list_crawls` → `sf_load_crawl`) or run a new one
(`sf_crawl` with `config_path` = `screaming-frog/crawl_default.seospiderconfig`). Wait until
`sf_crawl_progress` state is no longer `SpiderActiveState` — exports fail while the Spider is busy.

## Step 2 — Export to the SF base directory
`sf_export_seo_element_urls` with `{ "seo_element_name": "<H1|Hreflang|...>", "filter_name": "All",
"file_path": "<slug>-<element>-all.ndjson" }`. The MCP caps string responses at ~100 kB, so it
writes the NDJSON to a file in its own base dir (not the repo); the response's `path` field gives
the absolute location. The MCP usually exposes only the `All` filter — let the analyzer classify.

## Step 3 — Run the analyzer (reads the export, prints findings)
```bash
node ".claude/skills/<name>(SF)/<analyzer>.js" --input "<sf-base-dir>/<slug>-<element>-all.ndjson"
```
The analyzer reads that one NDJSON (or the same content on stdin) and prints a JSON report to
stdout. It writes no files. <Describe the JSON keys + issue categories + severity.>

## Step 4 — Report to the user (chat only)
Turn the JSON into a short plain-text summary (site URL, full/partial crawl, per-category counts,
top examples). Only mention categories with findings. Do not write a report file.
```

## Template B — Ahrefs skill `(Ahrefs)`

Copy into `.claude/skills/<name>(Ahrefs)/SKILL.md`. No `requires:` block — the skill drives its
own MCP calls. Family rules (naming, `doc`-first, USD-cents) live in `ahrefs/CLAUDE.md`.

```markdown
---
name: <name>(Ahrefs)
description: <one sentence on what data it pulls and produces>. Use when the user asks about <phrase>, <phrase>, <phrase>.
---

# <Skill Title> (Ahrefs)

Wraps the Ahrefs MCP `<tool-family>-*` tools into a reproducible raw → cleaned → summary
pipeline. Family-wide rules (including the prefix-neutral tool naming) live in `ahrefs/CLAUDE.md` —
read it once per session, then follow below.

## When to use this skill
The user asks anything about:
- <trigger phrase>
- <trigger phrase>

## Step 1 — Gather required inputs (ask the user if missing)
1. **`{project}`** — kebab-case slug used as the per-project subfolder under `data/` and `results/`.
2. **<domain / seed list / project>** — <how it's supplied>.
3. **<country / other params as needed>**.
Do not call any Ahrefs tool until inputs are confirmed.

## Step 2 — Fetch raw data via Ahrefs MCP
1. Call the Ahrefs MCP `doc` tool for each tool before its first use this session.
2. Call the appropriate tool(s); push numeric thresholds into the API `where` clause.
3. Save raw JSON exactly as returned (monetary values stay in USD cents):
   `ahrefs/<name>/data/{project}/{YYYY-MM-DD}.json`
   (`_v2`, `_v3` after the date for same-day reruns; `_{country}` for multi-market.)
4. If the response includes `render_with`, call that render tool too.

## Step 3 — Clean and filter
```bash
python ".claude/skills/<name>(Ahrefs)/<script>.py" \
  "ahrefs/<name>/data/{project}/{YYYY-MM-DD}.json" \
  "ahrefs/<name>/results/{project}/{YYYY-MM-DD}.json"
```
(If the skill takes a per-project config, keep it in `ahrefs/<name>/config/{project}.json` and
read it in the script — **do not edit the script** to change thresholds.)

## Step 4 — Write the Markdown summary
Read the filtered JSON and write a tight summary that answers the user's question:
`ahrefs/<name>/results/{project}/{YYYY-MM-DD}_summary.md`
```

## Multi-tool skills `(SF|Ahrefs)`

Combine both: run the stateless SF crawl→export→analyze flow for the SF side, drive Ahrefs MCP
calls for the Ahrefs side, and have the steps choreograph the cross-tool logic. Apply each family's
`CLAUDE.md` rules to its own part. Use a `(SF|Ahrefs)` (or `(SF|Ahrefs|GSC)`) tag.

---

## After creating — verify

1. Folder name == `name:` frontmatter, both ending in the same `(...)` tag.
2. Skill appears in the next session's `available-skills` reminder (restart/reload if needed).
3. A test request that should route here actually does — and doesn't steal requests from a
   neighboring skill.
4. Skills index row added to `CLAUDE.md`; `MEMORY.md` sub-section added.
```
