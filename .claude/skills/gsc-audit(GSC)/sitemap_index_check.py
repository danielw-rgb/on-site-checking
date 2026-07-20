#!/usr/bin/env python3
"""gsc-audit(GSC) — sitemap indexing check: cross-check XML sitemap URLs against GSC pages.

"Indexed on GSC" is APPROXIMATED by "appeared in GSC Search performance (got >=1 impression)"
in the analysis window. The Search Analytics API does not expose true index status, so a
sitemap URL absent from performance data is a *candidate* for not-indexed / zero-impressions
(it may be indexed but never shown). For authoritative status, spot-check with GSC's URL
Inspection in the UI.

The functions extract_sitemap_urls(), normalize_url(), load_gsc_pages(), analyze() are
imported by gsc_audit.py for the sitemap-indexing check (check 6). Can also be run standalone:
  python ".claude/skills/gsc-audit(GSC)/sitemap_index_check.py" \
    --sitemap https://example.com/sitemap.xml \
    --pages   gsc/gsc-audit/data/<client>/<date>_pages.ndjson \
    --output  gsc/gsc-audit/results/<client>/<date>_sitemap.json
"""
import argparse
import csv
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (OnsiteCheckingWorkflow GSC sitemap checker)"


def fetch_xml(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _localname(tag):
    return tag.split("}")[-1]  # strip XML namespace


def extract_sitemap_urls(url, _seen=None, _depth=0):
    """Return page URLs from a sitemap, recursing into <sitemapindex> entries."""
    if _seen is None:
        _seen = set()
    if url in _seen or _depth > 6:
        return []
    _seen.add(url)
    root = ET.fromstring(fetch_xml(url))
    urls = []
    if _localname(root.tag) == "sitemapindex":
        for sm in root:
            loc = next((c.text for c in sm if _localname(c.tag) == "loc"), None)
            if loc:
                urls += extract_sitemap_urls(loc.strip(), _seen, _depth + 1)
    else:  # <urlset>
        for u in root:
            loc = next((c.text for c in u if _localname(c.tag) == "loc"), None)
            if loc:
                urls.append(loc.strip())
    return urls


def normalize_url(u):
    """Canonical form for matching: drop scheme, fragment, query, trailing slash; lowercase host."""
    if not u:
        return u
    u = u.split("#", 1)[0].split("?", 1)[0]
    u = re.sub(r"^https?://", "", u, flags=re.I)
    # lowercase host only (keep path case, which can be significant)
    parts = u.split("/", 1)
    parts[0] = parts[0].lower()
    u = "/".join(parts)
    if len(u) > 1:
        u = u.rstrip("/")
    return u


def load_gsc_pages(path):
    pages = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line).get("page")
            if p:
                pages.add(normalize_url(p))
    return pages


def analyze(sitemap_urls, gsc_pages):
    """Return dict with counts + the sitemap URLs missing from GSC performance."""
    seen, rows = set(), []
    for u in sitemap_urls:
        n = normalize_url(u)
        if n in seen:
            continue
        seen.add(n)
        rows.append({"url": u, "in_gsc": n in gsc_pages})
    missing = [r["url"] for r in rows if not r["in_gsc"]]
    return {
        "sitemap_urls": len(rows),
        "in_gsc": len(rows) - len(missing),
        "missing": len(missing),
        "missing_urls": missing,
    }


def main():
    ap = argparse.ArgumentParser(description="Cross-check sitemap URLs vs GSC performance pages")
    ap.add_argument("--sitemap", required=True, help="Sitemap URL (or local .xml path)")
    ap.add_argument("--pages", required=True, help="GSC page-dimension NDJSON from gsc_fetch.py")
    ap.add_argument("--output", required=True, help="JSON report path")
    ap.add_argument("--csv", help="CSV path (default: alongside --output)")
    ap.add_argument("--top", type=int, default=50, help="Missing URLs kept in JSON samples")
    args = ap.parse_args()

    if re.match(r"^https?://", args.sitemap, re.I):
        sm_urls = extract_sitemap_urls(args.sitemap)
    else:
        root = ET.fromstring(open(args.sitemap, "rb").read())
        sm_urls = [c.text.strip() for u in root for c in u if _localname(c.tag) == "loc"]

    result = analyze(sm_urls, load_gsc_pages(args.pages))

    out = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    report = {"totals": {k: result[k] for k in ("sitemap_urls", "in_gsc", "missing")},
              "missing_sample": result["missing_urls"][: args.top],
              "missing_all": result["missing_urls"]}
    with open(out, "w") as f:
        json.dump(report, f, indent=2)

    csv_path = args.csv or os.path.splitext(out)[0] + ".csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Sitemap URL missing from GSC performance"])
        for u in result["missing_urls"]:
            w.writerow([u])

    print(f"Sitemap URLs: {result['sitemap_urls']}  In GSC perf: {result['in_gsc']}  "
          f"Missing: {result['missing']}")
    print(f"JSON -> {out}\nCSV  -> {csv_path}")


if __name__ == "__main__":
    main()
