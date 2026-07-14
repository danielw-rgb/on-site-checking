"""Cleaner + per-project filter for keywords-explorer-overview raw JSON.

Usage (run from repo root):
    python ".claude/skills/keyword-research(Ahrefs)/keyword_research.py" \
        ahrefs/keyword-research/data/<project>/<date>.json \
        ahrefs/keyword-research/results/<project>/<date>.json

Filter config (optional, per project):
    Place a JSON file at:
        ahrefs/keyword-research/config/{project}.json
    where {project} is the parent-folder name of the raw input
    (raw pulls live at ahrefs/keyword-research/data/{project}/{date}.json).
    If the file exists, its values are applied as filters.
    If not, all cleaned rows pass through.

Supported config keys (all optional; null or missing = ignore that knob):
    min_volume, max_volume                       (HK search volume)
    min_global_volume, max_global_volume         (global search volume)
    min_difficulty, max_difficulty               (KD, 0-100)
    min_cpc_usd, max_cpc_usd                     (CPC in dollars, after cents->USD)
    min_traffic_potential, max_traffic_potential
    exclude_branded            bool — drop rows with branded intent
    require_intents            list — keep row only if it has ANY of these intents
    exclude_intents            list — drop row if it has ANY of these intents
                               (valid intents: informational, navigational,
                                commercial, transactional, branded, local)

See filter_config/_example.json for a template.
"""

import json
import sys
from pathlib import Path

KEEP_FIELDS = [
    "keyword",
    "volume",
    "global_volume",
    "difficulty",
    "traffic_potential",
    "parent_topic",
    "parent_volume",
]

# Per-project filter configs live in the workspace, resolved relative to the
# repo root (the CWD the skill invokes this script from).
CONFIG_DIR = Path("ahrefs/keyword-research/config")


def clean_row(row: dict) -> dict:
    out = {k: row.get(k) for k in KEEP_FIELDS}
    cpc_cents = row.get("cpc")
    out["cpc_usd"] = round(cpc_cents / 100, 2) if cpc_cents is not None else None
    intents_obj = row.get("intents") or {}
    out["intents"] = [k for k, v in intents_obj.items() if v]
    serp = row.get("serp_features") or []
    out["serp_features"] = serp
    out["serp_feature_count"] = len(serp)
    return out


def _in_range(value, lo, hi) -> bool:
    if lo is not None and (value is None or value < lo):
        return False
    if hi is not None and (value is None or value > hi):
        return False
    return True


def passes(row: dict, cfg: dict) -> bool:
    if not _in_range(row.get("volume"), cfg.get("min_volume"), cfg.get("max_volume")):
        return False
    if not _in_range(row.get("global_volume"), cfg.get("min_global_volume"), cfg.get("max_global_volume")):
        return False
    if not _in_range(row.get("difficulty"), cfg.get("min_difficulty"), cfg.get("max_difficulty")):
        return False
    if not _in_range(row.get("cpc_usd"), cfg.get("min_cpc_usd"), cfg.get("max_cpc_usd")):
        return False
    if not _in_range(row.get("traffic_potential"), cfg.get("min_traffic_potential"), cfg.get("max_traffic_potential")):
        return False

    intents = set(row.get("intents") or [])
    if cfg.get("exclude_branded") and "branded" in intents:
        return False
    require_intents = cfg.get("require_intents") or []
    if require_intents and not (intents & set(require_intents)):
        return False
    exclude_intents = cfg.get("exclude_intents") or []
    if exclude_intents and (intents & set(exclude_intents)):
        return False
    return True


def derive_project(raw_path: Path) -> str:
    # New layout: raw pulls live at data/<project>/<date>.json, so the project
    # is the parent-folder name.
    return raw_path.resolve().parent.name


def load_config(raw_path: Path):
    project = derive_project(raw_path)
    cfg_path = CONFIG_DIR / f"{project}.json"
    if cfg_path.exists():
        return json.loads(cfg_path.read_text()), cfg_path
    return {}, None


def main(in_path: str, out_path: str) -> None:
    raw_path = Path(in_path)
    raw = json.loads(raw_path.read_text())
    cfg, cfg_path = load_config(raw_path)
    cleaned = [clean_row(r) for r in raw.get("keywords", [])]
    kept = [r for r in cleaned if passes(r, cfg)]
    kept.sort(key=lambda r: r.get("volume") or 0, reverse=True)
    out = {
        "source": raw.get("source"),
        "filter_config": {
            "path": str(cfg_path) if cfg_path else None,
            "values": cfg,
        },
        "input_row_count": len(cleaned),
        "row_count": len(kept),
        "keywords": kept,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    suffix = f" (filter: {cfg_path.name})" if cfg_path else " (no filter config — all rows kept)"
    print(f"Wrote {len(kept)} of {len(cleaned)} rows to {out_path}{suffix}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python keyword_research.py <raw.json> <filtered.json>")
    main(sys.argv[1], sys.argv[2])
