#!/usr/bin/env python3
"""gsc-audit(GSC): run all GSC checks off shared pulls and emit ONE combined report.

Checks:
  1. Keyword cannibalization      (analyze_cannibalization.py, bundled)        [needs query×page]
  2. Low-hanging fruit            (queries at pos 4–20 with room to grow)      [needs query×page]
  3. CTR opportunity              (good position, CTR below expected)          [needs query×page]
  4. Index hygiene / shouldn't    (pages getting impressions matching bad URL patterns) [needs page]
  5. Outdated content             (old year in query/URL still ranking)        [needs query×page]
  6. Sitemap indexing             (sitemap URLs absent from GSC performance)   [needs page + sitemap]

Outputs into --outdir: <date>_report.md (combined), one <date>_<check>.csv per check, and
<date>_audit.json. Reuses an existing query×page NDJSON (e.g. the cannibalization pull) — no
re-pull needed when the data is fresh.
"""
import argparse
import csv
import importlib.util
import json
import os
import re

HERE = os.path.dirname(__file__)

# --- approximate organic CTR by SERP position (blended desktop+mobile) -------
CTR_CURVE = {1: .28, 2: .15, 3: .10, 4: .07, 5: .05, 6: .04, 7: .03, 8: .025, 9: .02, 10: .018}

# Homepage / locale-root / index-file paths. The homepage ranks broadly for many
# queries, so it always shows keyword overlap + striking-distance rows with limited
# real CTR upside — we exclude it from checks 1–3 (cannibalization, LHF, CTR).
HOMEPAGE_RE = re.compile(r"^/(([a-z]{2}(-[a-z]{2})?)/?)?(index\.(html?|php))?$", re.I)


def is_homepage(page, base):
    """True if `page` (a normalized full URL) is the site root, a locale root
    (/en/, /zh-hk/), or an index file (/index.html, /index.php)."""
    p = page or ""
    if base and p.startswith(base):
        p = p[len(base):]
    p = re.sub(r"^https?://[^/]+", "", p)  # fallback: strip scheme+host
    return bool(HOMEPAGE_RE.match(p or "/"))


def expected_ctr(pos):
    p = max(1, int(round(pos)))
    if p in CTR_CURVE:
        return CTR_CURVE[p]
    return max(0.015 - 0.0005 * (p - 10), 0.002) if p > 10 else 0.01


def load_module(relpath, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_ndjson(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def aggregate_qp(rows, normalize):
    """Collapse query×page rows to one entry per (query, normalized-page)."""
    agg = {}
    for r in rows:
        q = r.get("query")
        if q is None:
            continue
        key = (q, normalize(r.get("page")))
        a = agg.get(key)
        if a is None:
            a = {"query": q, "page": key[1], "clicks": 0, "impressions": 0, "_pw": 0.0}
            agg[key] = a
        imp = r.get("impressions", 0)
        a["clicks"] += r.get("clicks", 0)
        a["impressions"] += imp
        a["_pw"] += r.get("position", 0) * imp
    out = []
    for a in agg.values():
        imp = a["impressions"]
        out.append({"query": a["query"], "page": a["page"], "clicks": a["clicks"],
                    "impressions": imp, "position": (a["_pw"] / imp) if imp else 0,
                    "ctr": (a["clicks"] / imp) if imp else 0})
    return out


# ----------------------------- checks ---------------------------------------

def check_cannibalization(cannib, qp_rows, args, exclude_re):
    pairs = cannib.analyze_pairs(qp_rows, args.cannib_min_impr, args.cannib_min_shared,
                                 True, True, exclude_re)
    home_skipped = 0
    if args.skip_homepage:
        kept = [p for p in pairs
                if not (is_homepage(p["page_a"], args.base) or is_homepage(p["page_b"], args.base))]
        home_skipped = len(pairs) - len(kept)
        pairs = kept
    rows = [{"Page A": p["page_a"].replace(args.base, ""), "Page B": p["page_b"].replace(args.base, ""),
             "Shared queries": p["shared_queries"], "Shared impr": p["shared_impressions"],
             "Overlap": f'{p["overlap"]*100:.0f}%',
             "Example queries": " · ".join(p["example_queries"][:3])} for p in pairs]
    note = (f" Homepage excluded ({home_skipped} pair{'s' if home_skipped != 1 else ''} involving "
            f"the homepage hidden — it ranks broadly and always shows overlap)." if home_skipped else "")
    return {"title": "Keyword cannibalization (page pairs ranking for the same queries)",
            "finding": f"{len(rows)} page pairs each rank for ≥{args.cannib_min_shared} of the same "
                       f"queries — same-intent duplicates (two takes on one topic / near-duplicate "
                       f"URLs), not broad terms. Brand & site: excluded." + note,
            "columns": ["Page A", "Page B", "Shared queries", "Shared impr", "Overlap", "Example queries"],
            "rows": rows}


def check_low_hanging_fruit(agg, args):
    cand = []
    home_skipped = 0
    for r in agg:
        if 4 <= r["position"] <= 20 and r["impressions"] >= args.lhf_min_impr:
            upside = r["impressions"] * expected_ctr(3) - r["clicks"]
            if upside > 0:
                if args.skip_homepage and is_homepage(r["page"], args.base):
                    home_skipped += 1
                    continue
                cand.append({**r, "upside": upside})
    cand.sort(key=lambda x: x["upside"], reverse=True)
    rows = [{"Query": c["query"], "Page": c["page"].replace(args.base, ""),
             "Impressions": c["impressions"], "Clicks": c["clicks"],
             "Position": round(c["position"], 1), "Est. extra clicks @top3": round(c["upside"])}
            for c in cand]
    note = (f" Homepage excluded ({home_skipped} striking-distance row{'s' if home_skipped != 1 else ''} "
            f"hidden — it ranks broadly for many queries)." if home_skipped else "")
    return {"title": "Low-hanging fruit (striking distance, position 4–20)",
            "finding": f"{len(rows)} query→page pairs rank 4–20 with ≥{args.lhf_min_impr} "
                       f"impressions — realistic candidates to push onto page 1 / top 3." + note,
            "columns": ["Query", "Page", "Impressions", "Clicks", "Position", "Est. extra clicks @top3"],
            "rows": rows}


def check_ctr_opportunity(agg, args):
    cand = []
    home_skipped = 0
    for r in agg:
        if r["position"] <= 10 and r["impressions"] >= args.ctr_min_impr:
            exp = expected_ctr(r["position"])
            if r["ctr"] < exp * args.ctr_factor:
                missed = (exp - r["ctr"]) * r["impressions"]
                if missed > 0:
                    if args.skip_homepage and is_homepage(r["page"], args.base):
                        home_skipped += 1
                        continue
                    cand.append({**r, "exp": exp, "missed": missed})
    cand.sort(key=lambda x: x["missed"], reverse=True)
    rows = [{"Query": c["query"], "Page": c["page"].replace(args.base, ""),
             "Impressions": c["impressions"], "Clicks": c["clicks"],
             "Position": round(c["position"], 1), "CTR": f"{c['ctr']*100:.1f}%",
             "Expected CTR": f"{c['exp']*100:.1f}%", "Missed clicks": round(c["missed"])}
            for c in cand]
    note = (f" Homepage excluded ({home_skipped} row{'s' if home_skipped != 1 else ''} hidden — its "
            f"CTR upside is limited)." if home_skipped else "")
    return {"title": "CTR opportunity (good position, low click-through)",
            "finding": f"{len(rows)} query→page pairs rank top-10 with ≥{args.ctr_min_impr} "
                       f"impressions but CTR below ~{int(args.ctr_factor*100)}% of expected — "
                       f"title/meta-description rewrites likely lift clicks." + note,
            "columns": ["Query", "Page", "Impressions", "Clicks", "Position", "CTR",
                        "Expected CTR", "Missed clicks"],
            "rows": rows}


def check_index_hygiene(page_rows, args):
    if page_rows is None:
        return {"title": "Index hygiene (indexed but shouldn't be)",
                "finding": "Skipped — no page-dimension pull provided.", "columns": [], "rows": []}
    bad = re.compile(args.bad_pattern, re.I)
    seen, cand = set(), []
    for r in page_rows:
        p = r.get("page", "")
        path = re.sub(r"^https?://[^/]+", "", p.split("?", 1)[0].split("#", 1)[0])
        if path in seen:
            continue
        seen.add(path)
        if bad.search(path):
            cand.append({"page": p, "impressions": r.get("impressions", 0),
                         "clicks": r.get("clicks", 0)})
    cand.sort(key=lambda x: x["impressions"], reverse=True)
    rows = [{"Page": c["page"].replace(args.base, ""), "Impressions": c["impressions"],
             "Clicks": c["clicks"]} for c in cand]
    return {"title": "Index hygiene (indexed but shouldn't be)",
            "finding": f"{len(rows)} pages getting impressions match no-index URL patterns "
                       f"(admin/cart/checkout/account/login/search/etc.). Review for noindex/robots.",
            "columns": ["Page", "Impressions", "Clicks"], "rows": rows}


def check_outdated(agg, args):
    # Plausible content years only (2015+) so specs like "2000 nits" / "2000 mAh" aren't
    # mistaken for years.
    year_re = re.compile(r"\b(201[5-9]|202\d)\b")
    cand = []
    for r in agg:
        url_years = [int(m) for m in year_re.findall(r["page"])]
        # If the page's own URL targets a current/newer year, it's current content (e.g. a
        # "2025 vs 2024" comparison) — the old year is just a reference. Skip it.
        if any(y >= args.outdated_before for y in url_years):
            continue
        q_old = [int(m) for m in year_re.findall(r["query"]) if int(m) < args.outdated_before]
        u_old = [y for y in url_years if y < args.outdated_before]
        if (q_old or u_old) and r["impressions"] >= args.outdated_min_impr:
            where = "+".join((["query"] if q_old else []) + (["url"] if u_old else []))
            cand.append({**r, "year": min(q_old + u_old), "where": where})
    cand.sort(key=lambda x: x["impressions"], reverse=True)
    rows = [{"Query": c["query"], "Page": c["page"].replace(args.base, ""), "Old year": c["year"],
             "Where": c["where"], "Impressions": c["impressions"], "Position": round(c["position"], 1)}
            for c in cand]
    return {"title": "Outdated content (old year still ranking)",
            "finding": f"{len(rows)} query→page pairs reference a year before {args.outdated_before} "
                       f"(in the query or URL) yet still draw impressions — refresh/repoint candidates.",
            "columns": ["Query", "Page", "Old year", "Where", "Impressions", "Position"], "rows": rows}


def check_sitemap(args, page_path):
    if not args.sitemap or page_path is None:
        return {"title": "Sitemap indexing (in sitemap, missing from GSC)",
                "finding": "Skipped — no --sitemap and/or no page-dimension pull provided.",
                "columns": [], "rows": []}
    sm = load_module("sitemap_index_check.py", "sitemap_index_check")
    if re.match(r"^https?://", args.sitemap, re.I):
        sm_urls = sm.extract_sitemap_urls(args.sitemap)
    else:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(open(args.sitemap, "rb").read())
        sm_urls = [c.text.strip() for u in root for c in u if sm._localname(c.tag) == "loc"]
    res = sm.analyze(sm_urls, sm.load_gsc_pages(page_path))
    rows = [{"Sitemap URL (missing from GSC performance)": u.replace(args.base, "")}
            for u in res["missing_urls"]]
    return {"title": "Sitemap indexing (in sitemap, missing from GSC)",
            "finding": f"{res['sitemap_urls']} sitemap URLs: {res['in_gsc']} appear in GSC "
                       f"performance, {res['missing']} do not (candidates for not-indexed / "
                       f"zero-impressions — confirm via URL Inspection).",
            "columns": ["Sitemap URL (missing from GSC performance)"], "rows": rows}


# ----------------------------- report ---------------------------------------

def _truncate(s, n=48):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def overview_points(key, res, n=3):
    """Point-form headline bullets for the overview, naming the key pages/issues per check."""
    rows = res["rows"]
    if not rows:
        return [res["finding"] if "Skipped" in res["finding"] else "None found."]
    pts = []
    if key == "cannibalization":
        for r in rows[:n]:
            pts.append(f'`{r["Page A"]}` ↔ `{r["Page B"]}` — {r["Shared queries"]} shared queries '
                       f'({r["Shared impr"]:,} impr, {r["Overlap"]} overlap)')
    elif key == "low_hanging_fruit":
        for r in rows[:n]:
            pts.append(f'`{r["Page"]}` for "{_truncate(r["Query"], 40)}" — pos {r["Position"]}, '
                       f'{r["Impressions"]:,} impr (~{r["Est. extra clicks @top3"]:,} extra clicks @top3)')
    elif key == "ctr_opportunity":
        for r in rows[:n]:
            pts.append(f'`{r["Page"]}` for "{_truncate(r["Query"], 40)}" — pos {r["Position"]}, '
                       f'CTR {r["CTR"]} vs {r["Expected CTR"]} expected (~{r["Missed clicks"]:,} clicks lost)')
    elif key == "index_hygiene":
        for r in rows[:5]:
            pts.append(f'`{r["Page"]}` — {r["Impressions"]:,} impr (should not be indexed?)')
    elif key == "outdated":
        for r in rows[:n]:
            pts.append(f'`{r["Page"]}` — "{_truncate(r["Query"], 40)}" references {r["Old year"]}')
    elif key == "sitemap_index":
        col = res["columns"][0]
        examples = ", ".join(f'`{r[col]}`' for r in rows[:4])
        pts.append(f'{len(rows)} sitemap URLs missing from GSC performance: {examples}'
                   + (" …" if len(rows) > 4 else ""))
    return pts


def md_table(columns, rows, limit):
    if not rows:
        return "_None found._\n"
    out = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for r in rows[:limit]:
        out.append("| " + " | ".join(str(r.get(c, "")) for c in columns) + " |")
    if len(rows) > limit:
        out.append(f"\n_…and {len(rows) - limit} more — see CSV._")
    return "\n".join(out) + "\n"


def write_csv(path, columns, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for r in rows:
            w.writerow([r.get(c, "") for c in columns])


def main():
    ap = argparse.ArgumentParser(description="GSC combined audit → one report")
    ap.add_argument("--client", required=True)
    ap.add_argument("--date", required=True, help="Run date, used in filenames (YYYY-MM-DD)")
    ap.add_argument("--query-page", required=True, dest="query_page", help="query×page NDJSON")
    ap.add_argument("--pages", help="page-dimension NDJSON (for checks 4 & 6)")
    ap.add_argument("--sitemap", help="Sitemap URL (or .xml path) for check 6")
    ap.add_argument("--outdir", required=True, help="Report output directory")
    ap.add_argument("--property", default="", help="Property, for the report header")
    ap.add_argument("--date-range", default="", dest="date_range", help="e.g. 2026-03-27 → 2026-06-27")
    ap.add_argument("--base", default="", help="Base URL stripped from displayed paths, e.g. https://x.com")
    ap.add_argument("--brand-regex", dest="brand_regex", default="", help="Brand/site: exclusion for cannibalization")
    ap.add_argument("--include-homepage", action="store_true", dest="include_homepage",
                    help="Keep the homepage (root / locale roots / index files) in checks 1–3. By "
                         "default it is excluded — it ranks broadly so it always shows overlap + "
                         "striking-distance rows with limited real CTR upside. Uses --base to detect it.")
    ap.add_argument("--top", type=int, default=10, help="Rows shown per section in the report")
    # thresholds
    ap.add_argument("--cannib-min-impr", type=int, default=10, dest="cannib_min_impr")
    ap.add_argument("--cannib-min-shared", type=int, default=3, dest="cannib_min_shared",
                    help="Min shared queries for a page pair to count as cannibalizing (default 3)")
    ap.add_argument("--lhf-min-impr", type=int, default=50, dest="lhf_min_impr")
    ap.add_argument("--ctr-min-impr", type=int, default=100, dest="ctr_min_impr")
    ap.add_argument("--ctr-factor", type=float, default=0.6, dest="ctr_factor")
    ap.add_argument("--outdated-before", type=int, default=2025, dest="outdated_before")
    ap.add_argument("--outdated-min-impr", type=int, default=10, dest="outdated_min_impr")
    ap.add_argument("--bad-pattern", dest="bad_pattern",
                    default=r"/(wp-admin|wp-login|admin|cart|checkout|account|my-account|login|"
                            r"signin|register|wishlist|search|orders|cdn-cgi)(/|$|\?)")
    args = ap.parse_args()
    args.skip_homepage = not args.include_homepage

    cannib = load_module("analyze_cannibalization.py", "cannib")
    exclude_re = re.compile(args.brand_regex, re.I) if args.brand_regex else None

    qp_rows = load_ndjson(args.query_page)
    page_rows = load_ndjson(args.pages) if args.pages else None
    agg = aggregate_qp(qp_rows, cannib.normalize_page)
    # Exclude brand / site: queries from the query-based opportunity checks too (not just
    # cannibalization) — brand terms distort striking-distance, CTR and outdated rankings.
    agg_q = [r for r in agg if not (exclude_re and exclude_re.search(r["query"]))]

    checks = [
        ("cannibalization", check_cannibalization(cannib, qp_rows, args, exclude_re)),
        ("low_hanging_fruit", check_low_hanging_fruit(agg_q, args)),
        ("ctr_opportunity", check_ctr_opportunity(agg_q, args)),
        ("index_hygiene", check_index_hygiene(page_rows, args)),
        ("outdated", check_outdated(agg_q, args)),
        ("sitemap_index", check_sitemap(args, args.pages)),
    ]

    os.makedirs(args.outdir, exist_ok=True)
    md = [f"# GSC Checking Result — {args.client}", ""]
    if args.property:
        md.append(f"- **Property:** {args.property}")
    if args.date_range:
        md.append(f"- **Date range:** {args.date_range}")
    md.append(f"- **Generated:** {args.date}")
    md.append(f"- **Source rows:** {len(qp_rows):,} query×page"
              + (f" · {len(page_rows):,} page" if page_rows is not None else ""))
    md.append("\n> \"Indexed on GSC\" = appeared in Search performance (got impressions); the API "
              "doesn't expose true index status. Confirm flagged items in the GSC UI.\n")

    # --- Overview (key findings, point form, naming the important pages) ---
    md.append("\n## Overview — key findings\n")
    for i, (key, res) in enumerate(checks, 1):
        md.append(f"**{i}. {res['title']} — {len(res['rows'])} found**\n")
        for p in overview_points(key, res):
            md.append(f"- {p}")
        md.append("")

    summary = {"client": args.client, "date": args.date, "checks": {}}
    for i, (key, res) in enumerate(checks, 1):
        csv_name = f"{args.date}_{key}.csv"
        if res["rows"]:
            write_csv(os.path.join(args.outdir, csv_name), res["columns"], res["rows"])
        md.append(f"\n## {i}. {res['title']}\n")
        md.append(res["finding"] + "\n")
        md.append(md_table(res["columns"], res["rows"], args.top))
        if res["rows"]:
            md.append(f"\n_Full list: `{csv_name}` ({len(res['rows'])} rows)._")
        summary["checks"][key] = {"title": res["title"], "count": len(res["rows"]),
                                  "finding": res["finding"]}

    report_path = os.path.join(args.outdir, f"{args.date}_report.md")
    with open(report_path, "w") as f:
        f.write("\n".join(md) + "\n")
    with open(os.path.join(args.outdir, f"{args.date}_audit.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print("GSC audit complete:")
    for key, res in checks:
        print(f"  {res['title']}: {len(res['rows'])}")
    print(f"Report -> {report_path}")


if __name__ == "__main__":
    main()
