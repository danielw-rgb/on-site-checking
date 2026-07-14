#!/usr/bin/env python3
"""Detect keyword cannibalization from GSC query+page rows.

Input: NDJSON produced by gsc/connector/gsc_fetch.py with dimensions `query,page`
(fields per row: query, page, clicks, impressions, ctr, position).

A query is flagged as "cannibalized" when >= min_pages of its URLs each clear a
minimum-impressions floor — i.e. Google is serving multiple of your pages for the
same search, splitting authority and clicks.

Outputs: a JSON report, a CSV (one row per competing query+page), and a stdout summary.
"""
import argparse
import csv
import json
import os
import re
from collections import defaultdict


def load_rows(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def normalize_page(url, strip_fragments=True, strip_query=True):
    """Collapse URL variants that GSC reports as separate rows for the SAME page:
    - `page#anchor` — SERP "jump to section" links;
    - `page?variant=…&utm_…&com_cvv=…` — Shopify/Merchant product-sync + tracking params.
    Stripping both prevents these from masquerading as multiple competing pages. Disable
    with strip_fragments=False / strip_query=False when a site uses them for distinct pages."""
    if not url:
        return url
    if strip_fragments:
        url = url.split("#", 1)[0]
    if strip_query:
        url = url.split("?", 1)[0]
    return url


def analyze(rows, min_impressions, min_pages, strip_fragments=True, strip_query=True, exclude_re=None):
    # query -> normalized page -> aggregated metrics
    by_query = defaultdict(dict)
    for r in rows:
        q = r.get("query")
        if q is None or (exclude_re and exclude_re.search(q)):
            continue
        page = normalize_page(r.get("page"), strip_fragments, strip_query)
        agg = by_query[q].get(page)
        if agg is None:
            agg = {"page": page, "clicks": 0, "impressions": 0, "_pos_weighted": 0.0}
            by_query[q][page] = agg
        impr = r.get("impressions", 0)
        agg["clicks"] += r.get("clicks", 0)
        agg["impressions"] += impr
        agg["_pos_weighted"] += r.get("position", 0) * impr  # impression-weighted position

    findings = []
    for q, pagemap in by_query.items():
        pages = []
        for agg in pagemap.values():
            impr = agg["impressions"]
            pages.append({
                "page": agg["page"],
                "clicks": agg["clicks"],
                "impressions": impr,
                "ctr": (agg["clicks"] / impr) if impr else 0,
                "position": (agg["_pos_weighted"] / impr) if impr else 0,
            })
        competing = [p for p in pages if p["impressions"] >= min_impressions]
        if len(competing) < min_pages:
            continue
        competing.sort(key=lambda p: p["impressions"], reverse=True)
        total_clicks = sum(p["clicks"] for p in competing)
        total_impr = sum(p["impressions"] for p in competing)
        # How evenly impressions split across competing pages: 0 = one page dominates,
        # -> 1 = evenly shared (worse cannibalization).
        spread = (1.0 - max(p["impressions"] for p in competing) / total_impr) if total_impr else 0.0
        findings.append({
            "query": q,
            "num_pages": len(competing),
            "total_clicks": total_clicks,
            "total_impressions": total_impr,
            "impression_spread": round(spread, 3),
            "best_position": round(min(p["position"] for p in competing), 1),
            "worst_position": round(max(p["position"] for p in competing), 1),
            # Severity scales with how much traffic is at stake AND how evenly it's split.
            "severity": round(total_impr * spread, 1),
            "pages": [{
                "page": p["page"],
                "clicks": p["clicks"],
                "impressions": p["impressions"],
                "ctr": round(p["ctr"], 4),
                "position": round(p["position"], 1),
            } for p in competing],
        })
    findings.sort(key=lambda x: x["severity"], reverse=True)
    return findings


def analyze_pairs(rows, min_impressions=10, min_shared_queries=3,
                  strip_fragments=True, strip_query=True, exclude_re=None):
    """Page-pair cannibalization: find PAIRS of pages that rank for many of the SAME queries.

    This targets same-intent duplication (two reviews of one product, two blogs on one watch,
    near-duplicate URLs) rather than broad head terms where a product + collection + blog all
    legitimately mention the same word. A review vs a how-to share few queries → not flagged;
    two takes on the same topic share many → flagged. Score = number of shared queries.
    """
    from itertools import combinations
    qmap = {}  # query -> {normalized_page: impressions}
    for r in rows:
        q = r.get("query")
        if q is None or (exclude_re and exclude_re.search(q)):
            continue
        page = normalize_page(r.get("page"), strip_fragments, strip_query)
        qmap.setdefault(q, {})
        qmap[q][page] = qmap[q].get(page, 0) + r.get("impressions", 0)

    pair = {}        # (a, b) -> {shared, impr, queries}
    page_qcount = {}  # page -> number of queries it competes on
    for q, pages in qmap.items():
        comp = [(p, imp) for p, imp in pages.items() if imp >= min_impressions]
        for p, _ in comp:
            page_qcount[p] = page_qcount.get(p, 0) + 1
        for (a, ia), (b, ib) in combinations(sorted(comp), 2):
            d = pair.setdefault((a, b), {"shared": 0, "impr": 0.0, "queries": []})
            d["shared"] += 1
            d["impr"] += min(ia, ib)
            d["queries"].append({"query": q, "impr": ia + ib})

    findings = []
    for (a, b), d in pair.items():
        if d["shared"] < min_shared_queries:
            continue
        union = page_qcount[a] + page_qcount[b] - d["shared"]
        overlap = (d["shared"] / union) if union else 0
        d["queries"].sort(key=lambda x: x["impr"], reverse=True)
        findings.append({
            "page_a": a, "page_b": b,
            "shared_queries": d["shared"],
            "shared_impressions": int(d["impr"]),
            "overlap": round(overlap, 3),
            # Rank by duplication strength (overlap) × traffic at stake (shared impressions),
            # so same-intent duplicates rise above broad pages that merely share some queries.
            "score": round(overlap * d["impr"], 1),
            "example_queries": [x["query"] for x in d["queries"][:5]],
        })
    findings.sort(key=lambda x: x["score"], reverse=True)
    return findings


def main():
    ap = argparse.ArgumentParser(description="GSC keyword cannibalization analyzer")
    ap.add_argument("--input", required=True, help="NDJSON of query,page rows from gsc_fetch.py")
    ap.add_argument("--output", required=True, help="JSON report path")
    ap.add_argument("--csv", help="CSV path (default: alongside --output)")
    ap.add_argument("--min-impressions", type=int, default=10, dest="min_impressions",
                    help="Min impressions for a page to count as competing (default 10)")
    ap.add_argument("--min-pages", type=int, default=2, dest="min_pages",
                    help="Min competing pages to flag a query (default 2)")
    ap.add_argument("--keep-fragments", action="store_true",
                    help="Keep page#anchor URLs distinct (default: strip #fragments so anchor "
                         "variants of the same page don't count as cannibalization)")
    ap.add_argument("--keep-query", action="store_true",
                    help="Keep ?query-string URLs distinct (default: strip them so variant/utm/"
                         "tracking params of the same page don't count as cannibalization)")
    ap.add_argument("--exclude-query-regex", dest="exclude_query_regex",
                    help="Drop queries matching this regex (e.g. brand terms / 'site:'), case-insensitive")
    ap.add_argument("--min-shared-queries", type=int, default=3, dest="min_shared_queries",
                    help="Page-pair mode: min shared queries for two pages to count as cannibalizing (default 3)")
    ap.add_argument("--legacy-query-view", action="store_true", dest="legacy",
                    help="Use the old query-centric view (1 query → N pages) instead of the "
                         "default page-pair view (2 pages → shared queries)")
    ap.add_argument("--top", type=int, default=20, help="Number of samples kept in report (default 20)")
    args = ap.parse_args()

    exclude_re = re.compile(args.exclude_query_regex, re.I) if args.exclude_query_regex else None
    strip_fragments = not args.keep_fragments
    strip_query = not args.keep_query
    rows = load_rows(args.input)
    out = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    csv_path = args.csv or os.path.splitext(out)[0] + ".csv"

    if args.legacy:
        findings = analyze(rows, args.min_impressions, args.min_pages, strip_fragments, strip_query, exclude_re)
        with open(out, "w") as f:
            json.dump({"mode": "query", "samples": findings[: args.top], "full": findings}, f, indent=2)
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Query", "Page", "Clicks", "Impressions", "CTR", "Position", "Num Pages", "Severity"])
            for fnd in findings:
                for pg in fnd["pages"]:
                    w.writerow([fnd["query"], pg["page"], pg["clicks"], pg["impressions"],
                                pg["ctr"], pg["position"], fnd["num_pages"], fnd["severity"]])
        print(f"[query view] Cannibalized queries: {len(findings)}")
    else:
        pairs = analyze_pairs(rows, args.min_impressions, args.min_shared_queries,
                              strip_fragments, strip_query, exclude_re)
        with open(out, "w") as f:
            json.dump({"mode": "pairs", "min_shared_queries": args.min_shared_queries,
                       "samples": pairs[: args.top], "full": pairs}, f, indent=2)
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Page A", "Page B", "Shared queries", "Shared impressions", "Overlap",
                        "Example queries"])
            for p in pairs:
                w.writerow([p["page_a"], p["page_b"], p["shared_queries"], p["shared_impressions"],
                            f'{p["overlap"]*100:.0f}%', " | ".join(p["example_queries"])])
        print(f"[page-pair view] Cannibalizing page pairs (>= {args.min_shared_queries} shared queries): {len(pairs)}")
        for p in pairs[:10]:
            print(f"  {p['shared_queries']:>3} shared, {p['shared_impressions']:>7} impr  "
                  f"{p['page_a']}  <->  {p['page_b']}")
    print(f"JSON -> {out}\nCSV  -> {csv_path}")


if __name__ == "__main__":
    main()
