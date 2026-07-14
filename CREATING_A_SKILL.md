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
- [ ] **SF skills only:** declare profile fields / exports in a `requires:` block (see template).
- [ ] **Ahrefs skills only:** no `requires:` block — each skill drives its own MCP calls in its steps.
- [ ] Verify routing: the `description` should make it obvious which user requests map here and
      not collide with an existing skill.

---

## Template A — Screaming Frog skill `(SF)`

Copy into `.claude/skills/<name>(SF)/SKILL.md`. Replace every `<…>`.
The `requires:` block is read by the universal workflow (`screaming-frog/CLAUDE.md`) steps 3 + 4a,
which check the profile and produce each export on demand.

```markdown
---
name: <name>(SF)
description: <one sentence on what it audits>. Use when the user asks about <phrase>, <phrase>, <phrase>.
requires:
  profile: {}                      # or e.g. { near_duplicates: true } to require a profile field
  exports:
    - slug: <export-slug>          # used as the NDJSON filename in the run folder
      source:
        type: seo_element          # or bulk_export — see CRAWL_DEFAULTS.md / SF MCP docs
        element: <H1|Title|...>
        filter: <Missing|Duplicate|...>   # confirm via sf_list_available_filters_for_seo_element
---

# <Skill Title>

<One-paragraph summary of what it flags and from which crawl data.>

## When to use this skill
The user asks anything about:
- <trigger phrase>
- <trigger phrase>

## Prerequisites (from root CLAUDE.md)
The universal SF workflow in the root `CLAUDE.md` must already be complete for this run:
1. The user has provided `SITE_URL`.
2. `<domain-slug>` and `<run-id>` are set.
3. `sf_crawl` has completed (or `sf_load_crawl` reused a prior crawl).
4. The run manifest exists at `./screaming-frog/crawls/<domain-slug>/<run-id>/manifest.json`.
If any are missing, follow the root `CLAUDE.md` workflow first.

## Step 1 — Resolve exports (per CLAUDE.md step 4a)
For each export in the frontmatter, step 4a calls `manifest.js --has`, exports the NDJSON if
missing, and registers it. After this step the files exist at:
- `./screaming-frog/crawls/<domain-slug>/<run-id>/<export-slug>.ndjson`

## Step 2 — Run the analyzer
```bash
node .claude/skills/<name>/<analyzer>.js \
  --run-dir ./screaming-frog/crawls/<domain-slug>/<run-id> \
  --output  ./screaming-frog/reports/<domain-slug>/<run-id>/<name>-analysis.json
```
<Describe the JSON/CSV layout the analyzer writes.>

## Step 3 — Interpret the output
<Top-level JSON keys and what each issue category means + severity guidance.>

## Step 4 — Save the summary
Write a human-readable summary to:
`./screaming-frog/reports/<domain-slug>/<run-id>/<name>-summary.txt`
Include: site URL, crawl date, crawl ID, total pages crawled (from manifest), per-category counts,
top example URLs, and a pointer to the analysis JSON.
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

Wraps `mcp__claude_ai_Ahrefs__<tool-family>-*` into a reproducible raw → cleaned → summary
pipeline. Family-wide rules live in `ahrefs/CLAUDE.md` — read it once per session, then follow below.

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
1. Call `mcp__claude_ai_Ahrefs__doc` for each tool before its first use this session.
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

Combine both: declare the `requires:` block for the SF side, drive Ahrefs MCP calls in the steps,
and have the steps choreograph the cross-tool logic. Apply each family's `CLAUDE.md` rules to its
own part. Use a `(SF|Ahrefs)` (or `(SF|Ahrefs|GSC)`) tag.

---

## After creating — verify

1. Folder name == `name:` frontmatter, both ending in the same `(...)` tag.
2. Skill appears in the next session's `available-skills` reminder (restart/reload if needed).
3. A test request that should route here actually does — and doesn't steal requests from a
   neighboring skill.
4. Skills index row added to `CLAUDE.md`; `MEMORY.md` sub-section added.
```
