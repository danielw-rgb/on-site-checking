"""Cleaner for site-explorer-organic-keywords raw JSON, focused on keyword
cannibalization (one keyword ranking on multiple URLs of the same site).

Usage (run from repo root):
    python ".claude/skills/site-audit(Ahrefs)/site_audit.py" \
        ahrefs/site-audit/data/<project>/<date>.json \
        ahrefs/site-audit/results/<project>/<date>.json

What it does:
    - Reads the raw Ahrefs response saved under ahrefs/site-audit/data/<project>/.
    - For each keyword, dedupes `all_positions` by base URL (fragments like
      "/page/#h-section" collapse into "/page/"). Ahrefs counts each anchor
      as a separate position, which inflates the cannibalization signal.
    - Keeps only keywords whose deduped URL count is >= 2 (true page-level
      cannibalization).
    - Converts CPC from USD cents to USD.
    - Sorts by sum_traffic desc, then volume desc.
"""

import json
import sys
from pathlib import Path
from urllib.parse import urldefrag

MIN_UNIQUE_URLS = 2


def _strip_fragment(url: str) -> str:
    return urldefrag(url).url if url else url


def _dedupe_positions(positions):
    """Collapse fragment-only duplicates; keep best (lowest non-zero) position per URL."""
    by_url = {}
    for p in positions or []:
        url = _strip_fragment(p.get("url") or "")
        if not url:
            continue
        pos = p.get("position")
        current = by_url.get(url)
        # Treat 0 (sitelink/feature) as worse than any real organic rank, but keep it
        # if it's the only position seen.
        if current is None:
            by_url[url] = pos
        else:
            if pos is None:
                continue
            if current is None or current == 0 or (pos and pos < current):
                by_url[url] = pos
    return [{"position": pos, "url": url} for url, pos in by_url.items()]


def clean_row(row: dict) -> dict:
    ranking_urls = _dedupe_positions(row.get("all_positions"))
    ranking_urls.sort(key=lambda r: (r["position"] is None or r["position"] == 0, r["position"] or 9999))
    cpc_cents = row.get("cpc")
    return {
        "keyword": row.get("keyword"),
        "volume": row.get("volume"),
        "keyword_difficulty": row.get("keyword_difficulty"),
        "cpc_usd": round(cpc_cents / 100, 2) if cpc_cents is not None else None,
        "sum_traffic": row.get("sum_traffic"),
        "best_position": row.get("best_position"),
        "best_position_url": row.get("best_position_url"),
        "best_position_kind": row.get("best_position_kind"),
        "serp_target_positions_count_raw": row.get("serp_target_positions_count"),
        "unique_url_count": len(ranking_urls),
        "ranking_urls": ranking_urls,
    }


def main(in_path: str, out_path: str) -> None:
    raw_path = Path(in_path)
    raw = json.loads(raw_path.read_text())
    cleaned = [clean_row(r) for r in raw.get("keywords", [])]
    kept = [r for r in cleaned if r["unique_url_count"] >= MIN_UNIQUE_URLS]
    kept.sort(key=lambda r: (r.get("sum_traffic") or 0, r.get("volume") or 0), reverse=True)
    out = {
        "source": raw.get("source"),
        "filter": {
            "min_unique_urls": MIN_UNIQUE_URLS,
            "note": "URL fragments (#...) collapsed before counting; keeps only keywords with >=2 distinct pages ranking.",
        },
        "input_row_count": len(cleaned),
        "row_count": len(kept),
        "keywords": kept,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"Wrote {len(kept)} of {len(cleaned)} rows to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python site_audit.py <raw.json> <filtered.json>")
    main(sys.argv[1], sys.argv[2])
