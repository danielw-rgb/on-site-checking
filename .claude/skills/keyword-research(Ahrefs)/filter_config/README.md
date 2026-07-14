# Keyword Research — Filter Config Guide

This folder holds per-project filter rules for the keyword-research cleaning script.

## Rule of thumb

**If the Ahrefs API can apply the filter at fetch time, do it there.** API-side filters cost zero extra units and you don't ship rows you'd throw away. Only put a filter here if the API can't express it cleanly, or if you want to re-filter an existing raw file without re-fetching.

## Which filter goes where

### Push to the Ahrefs API call (`where` / `order_by` / `select`)

Use these at fetch time — they're cheaper and faster.

| What you want                              | API `where` example                                   | Notes                                      |
| ------------------------------------------ | ------------------------------------------------------ | ------------------------------------------ |
| Volume threshold                           | `{"field":"volume","is":["gt",200]}`                   | HK / country volume                        |
| Global volume threshold                    | `{"field":"global_volume","is":["gte",1000]}`          |                                            |
| Difficulty cap                             | `{"field":"difficulty","is":["lte",30]}`               | KD on 0–100 scale                          |
| CPC threshold                              | `{"field":"cpc","is":["gt",500]}`                      | **CPC is in USD cents** in the API (500 = $5) |
| Traffic potential threshold                | `{"field":"traffic_potential","is":["gt",100]}`        |                                            |
| Word count                                 | `{"field":"word_count","is":["gte",2]}`                |                                            |
| Combine                                    | `{"and":[{...}, {...}]}` or `{"or":[{...}, {...}]}`    |                                            |
| Sort                                       | `order_by: "volume:desc"`                              |                                            |
| Pick columns                               | `select: "keyword,volume,difficulty,..."`              |                                            |

### Keep in `filter_config/{project-name}.json` (script-side)

These are the knobs the API can't do well — the `intents` field is a nested object, so `where`-based filtering is awkward. Also use these when you want to re-cut an existing raw file without spending more units.

| Config key             | What it does                                              |
| ---------------------- | --------------------------------------------------------- |
| `exclude_branded`      | Drop rows where `intents.branded == true`                 |
| `require_intents`      | Keep row only if it has ANY of the listed intents         |
| `exclude_intents`      | Drop row if it has ANY of the listed intents              |

Valid intents: `informational`, `navigational`, `commercial`, `transactional`, `branded`, `local`.

### Both work, but prefer the API side

These keys exist in the config for flexibility (e.g. you fetched without a filter and now want to re-cut), but if you can, prefer the API:

- `min_volume`, `max_volume`
- `min_global_volume`, `max_global_volume`
- `min_difficulty`, `max_difficulty`
- `min_cpc_usd`, `max_cpc_usd` (script uses USD; API uses cents)
- `min_traffic_potential`, `max_traffic_potential`

Don't set the same threshold in both places unless you're documenting it deliberately — pick one home for each filter.

## File naming

- `{project-name}.json` — the script auto-loads this based on the raw file's project prefix.
- `_example.json` — template showing every supported key.
- `README.md` — this file.
