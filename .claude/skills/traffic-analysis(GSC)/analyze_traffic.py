#!/usr/bin/env python3
"""Summarise GSC organic traffic for weekly + monthly reporting, in three layers:
  1. OVERALL       — whole-site traffic (from the `date` pull, incl. anonymized queries).
  2. TARGET URLs   — per-page traffic for a saved watchlist (from the `page,date` pull).
  3. TARGET QUERIES— per-keyword position/traffic for a saved watchlist (from `query,date`).

The URL + keyword watchlists live in a per-client targets file (see --targets-file) so the
same lists are reused every run; --target-keywords can add ad-hoc terms on top.

Consumes NDJSON pulls from gsc/connector/gsc_fetch.py:
  - REQUIRED  --date-file   : dimensions `date`        (overall site totals)
  - REQUIRED  --query-file  : dimensions `query,date`  (target queries + query movers)
  - OPTIONAL  --page-file   : dimensions `page,date`   (target URLs + page movers) — REQUIRED
                              if the run has any target URLs.

Two comparisons ending at the latest date in the data (`asof`, GSC lags ~2-3 days):
  - Weekly : last 7 days vs the 7 days before.
  - Monthly: last 28 days vs the previous 28 days (--month-mode 28d, default), or
             current calendar month-to-date vs the same days last month (calendar).

Position is impression-weighted when aggregated across days (GSC's own method). CTR is
recomputed as clicks / impressions per window (never averaged).

Optional ad-hoc focus (headline only): --query-filter / --page-filter restrict the OVERALL
block to matching queries/pages (excludes anonymized). The target layers are unaffected.

Outputs: a JSON report, CSVs alongside it, and a stdout summary. The client-facing prose is
written separately by the skill from these numbers.
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
from collections import defaultdict


# ---------- io ----------

def load_rows(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def dedupe(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ---------- normalizers ----------

def norm_query(s):
    return (s or "").strip().lower()


def norm_url(u):
    """Collapse URL variants GSC reports separately: #fragment, ?query, trailing slash, case."""
    if not u:
        return u
    u = u.split("#", 1)[0].split("?", 1)[0]
    if len(u) > 1 and u.endswith("/"):
        u = u[:-1]
    return u.lower()


# ---------- window math ----------

def first_of_month(d):
    return d.replace(day=1)


def last_of_prev_month(d):
    return first_of_month(d) - dt.timedelta(days=1)


def add_months_back(d):
    return first_of_month(last_of_prev_month(d))


class Window:
    def __init__(self, label, start, end):
        self.label, self.start, self.end = label, start, end

    def contains(self, d):
        return self.start <= d <= self.end

    def days(self):
        return (self.end - self.start).days + 1

    def as_dict(self):
        return {"label": self.label, "from": self.start.isoformat(),
                "to": self.end.isoformat(), "days": self.days()}


def weekly_windows(asof):
    cur = Window("last 7 days", asof - dt.timedelta(days=6), asof)
    prev = Window("previous 7 days", asof - dt.timedelta(days=13), asof - dt.timedelta(days=7))
    return cur, prev


def monthly_windows(asof, mode):
    if mode == "calendar":
        cur_start = first_of_month(asof)
        cur = Window(asof.strftime("%B %Y") + " (MTD)", cur_start, asof)
        prev_month_start = add_months_back(asof)
        span = (asof - cur_start).days
        prev_end = prev_month_start + dt.timedelta(days=span)
        month_end = last_of_prev_month(asof)
        if prev_end > month_end:
            prev_end = month_end
        prev = Window(prev_month_start.strftime("%b %d") + "–" + prev_end.strftime("%b %d"),
                      prev_month_start, prev_end)
        return cur, prev
    cur = Window("last 28 days", asof - dt.timedelta(days=27), asof)
    prev = Window("previous 28 days", asof - dt.timedelta(days=55), asof - dt.timedelta(days=28))
    return cur, prev


# ---------- aggregation ----------

def agg(rows, window):
    """Sum clicks/impressions over a window; impression-weight position; recompute CTR."""
    clicks = impr = pw = 0.0
    for r in rows:
        if not window.contains(parse_date(r["date"])):
            continue
        i = r.get("impressions", 0) or 0
        clicks += r.get("clicks", 0) or 0
        impr += i
        pw += (r.get("position", 0) or 0) * i
    ctr = (clicks / impr) if impr else 0.0
    position = (pw / impr) if impr else 0.0
    return {"clicks": round(clicks), "impressions": round(impr),
            "ctr": round(ctr, 4), "position": round(position, 1)}


def pct(cur, prev):
    if prev in (0, 0.0, None):
        return None
    return round((cur - prev) / prev * 100, 1)


def compare(cur_m, prev_m):
    d = {}
    for k in ("clicks", "impressions"):
        d[k] = {"current": cur_m[k], "previous": prev_m[k],
                "abs": round(cur_m[k] - prev_m[k]), "pct": pct(cur_m[k], prev_m[k])}
    d["ctr"] = {"current": cur_m["ctr"], "previous": prev_m["ctr"],
                "abs_points": round((cur_m["ctr"] - prev_m["ctr"]) * 100, 2),
                "pct": pct(cur_m["ctr"], prev_m["ctr"])}
    delta = round(cur_m["position"] - prev_m["position"], 1)  # lower = better
    d["position"] = {"current": cur_m["position"], "previous": prev_m["position"],
                     "abs": delta, "improved": delta < 0}
    return d


def window_block(rows, cur_win, prev_win):
    cur_m, prev_m = agg(rows, cur_win), agg(rows, prev_win)
    return {"current": {**cur_win.as_dict(), **cur_m},
            "previous": {**prev_win.as_dict(), **prev_m},
            "delta": compare(cur_m, prev_m)}


# ---------- entity (query / URL) tracking ----------

def index_by_key(rows, key, normfn):
    idx = defaultdict(list)
    for r in rows:
        idx[normfn(r.get(key, "") or "")].append(r)
    return idx


def latest_entry(entries):
    best = None
    for r in entries:
        d = parse_date(r["date"])
        if best is None or d > best[0]:
            best = (d, r)
    if best is None:
        return None
    d, r = best
    return {"date": d.isoformat(), "position": round(r.get("position", 0) or 0, 1),
            "clicks": round(r.get("clicks", 0) or 0),
            "impressions": round(r.get("impressions", 0) or 0)}


def _clicks_delta(cur, prev):
    if cur is None and prev is None:
        return None
    return round((cur["clicks"] if cur else 0) - (prev["clicks"] if prev else 0))


def track_targets(rows, key, targets, normfn, wk, wkp, mo, mop, first_page=False):
    idx = index_by_key(rows, key, normfn)
    out = []
    for t in targets:
        e = idx.get(normfn(t), [])
        wc, wp = agg(e, wk) if e else None, agg(e, wkp) if e else None
        mc, mp = agg(e, mo) if e else None, agg(e, mop) if e else None
        # agg() returns zeros (not None) even for empty windows; treat all-zero impr as None
        wc = wc if (wc and wc["impressions"]) else None
        wp = wp if (wp and wp["impressions"]) else None
        mc = mc if (mc and mc["impressions"]) else None
        mp = mp if (mp and mp["impressions"]) else None
        movement = round(wp["position"] - wc["position"], 1) if (wc and wp) else None
        rec = {
            key: t, "found": bool(wc or mc or e),
            "weekly": {"current": wc, "previous": wp,
                       "clicks_delta": _clicks_delta(wc, wp), "position_movement": movement},
            "monthly": {"current": mc, "previous": mp, "clicks_delta": _clicks_delta(mc, mp)},
            "latest": latest_entry(e) if e else None,
        }
        if first_page:
            ref = wc or mc or rec["latest"]
            rec["first_page"] = (ref["position"] <= 10.0) if ref else None
        out.append(rec)
    return out


# ---------- movers ----------

def filter_rows(rows, key, pattern):
    if not pattern:
        return rows
    rx = re.compile(pattern, re.I)
    return [r for r in rows if rx.search(r.get(key, "") or "")]


def movers(rows, key, cur_win, prev_win, top):
    cur = defaultdict(lambda: [0.0, 0.0, 0.0])
    prev = defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in rows:
        d = parse_date(r["date"])
        bucket = cur if cur_win.contains(d) else prev if prev_win.contains(d) else None
        if bucket is None:
            continue
        k = r.get(key, "")
        i = r.get("impressions", 0) or 0
        bucket[k][0] += r.get("clicks", 0) or 0
        bucket[k][1] += i
        bucket[k][2] += (r.get("position", 0) or 0) * i
    out = []
    for k in set(cur) | set(prev):
        cc, ci, cpw = cur.get(k, [0, 0, 0])
        pc, pi, ppw = prev.get(k, [0, 0, 0])
        out.append({key: k, "clicks_current": round(cc), "clicks_previous": round(pc),
                    "clicks_delta": round(cc - pc), "impressions_current": round(ci),
                    "position_current": round(cpw / ci, 1) if ci else None,
                    "position_previous": round(ppw / pi, 1) if pi else None})
    gainers = sorted(out, key=lambda x: x["clicks_delta"], reverse=True)[:top]
    losers = [x for x in sorted(out, key=lambda x: x["clicks_delta"]) if x["clicks_delta"] < 0][:top]
    return {"gainers": gainers, "losers": losers}


# ---------- csv ----------

def write_windows_csv(path, overall):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["comparison", "window", "from", "to", "days",
                    "clicks", "impressions", "ctr", "position"])
        for name in ("weekly", "monthly"):
            for role in ("current", "previous"):
                b = overall[name][role]
                w.writerow([name, b["label"], b["from"], b["to"], b["days"],
                            b["clicks"], b["impressions"], b["ctr"], b["position"]])


def _cell(block, role, field):
    m = block.get(role)
    return m.get(field) if m else None


def write_targets_csv(path, key, targets, first_page):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        head = [key, "found"]
        if first_page:
            head.append("first_page")
        head += ["wk_clicks", "wk_clicks_prev", "wk_clicks_delta", "wk_pos", "wk_pos_move",
                 "mo_clicks", "mo_clicks_prev", "mo_clicks_delta", "mo_pos",
                 "latest_date", "latest_pos"]
        w.writerow(head)
        for t in targets:
            wk, mo, lt = t["weekly"], t["monthly"], (t["latest"] or {})
            row = [t[key], t["found"]]
            if first_page:
                row.append(t.get("first_page"))
            row += [_cell(wk, "current", "clicks"), _cell(wk, "previous", "clicks"),
                    wk["clicks_delta"], _cell(wk, "current", "position"), wk["position_movement"],
                    _cell(mo, "current", "clicks"), _cell(mo, "previous", "clicks"),
                    mo["clicks_delta"], _cell(mo, "current", "position"),
                    lt.get("date"), lt.get("position")]
            w.writerow(row)


def write_movers_csv(path, key, mv):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["direction", key, "clicks_current", "clicks_previous", "clicks_delta",
                    "impressions_current", "position_current", "position_previous"])
        for direction in ("gainers", "losers"):
            for m in mv[direction]:
                w.writerow([direction, m[key], m["clicks_current"], m["clicks_previous"],
                            m["clicks_delta"], m["impressions_current"],
                            m["position_current"], m["position_previous"]])


# ---------- main ----------

def load_targets_file(path):
    with open(path) as f:
        cfg = json.load(f)
    return cfg.get("target_urls", []), cfg.get("target_keywords", [])


def main():
    ap = argparse.ArgumentParser(description="Summarise GSC traffic (overall + target URLs + target queries)")
    ap.add_argument("--date-file", required=True, dest="date_file")
    ap.add_argument("--query-file", required=True, dest="query_file")
    ap.add_argument("--page-file", dest="page_file", help="Required if there are target URLs")
    ap.add_argument("--output", required=True)
    ap.add_argument("--targets-file", dest="targets_file",
                    help="Per-client JSON with target_urls + target_keywords")
    ap.add_argument("--target-keywords", default="", dest="target_keywords",
                    help="Extra comma-separated queries (added to the targets file)")
    ap.add_argument("--asof", help="Report end date YYYY-MM-DD (default: latest in data)")
    ap.add_argument("--month-mode", default="28d", choices=["28d", "calendar"], dest="month_mode",
                    help="28d = rolling last 28 days vs previous 28 (default); "
                         "calendar = current month-to-date vs same days last month")
    ap.add_argument("--query-filter", dest="query_filter",
                    help="Regex — restrict the OVERALL block to matching queries (ad-hoc topic)")
    ap.add_argument("--page-filter", dest="page_filter",
                    help="Regex — restrict the OVERALL block to matching pages (needs --page-file)")
    ap.add_argument("--top", type=int, default=10, help="Top-N movers each direction")
    ap.add_argument("--client", default="")
    ap.add_argument("--property", default="")
    args = ap.parse_args()

    date_rows = load_rows(args.date_file)
    query_rows = load_rows(args.query_file)
    page_rows = load_rows(args.page_file) if args.page_file else []

    all_dates = [parse_date(r["date"]) for r in date_rows + query_rows if r.get("date")]
    if not all_dates:
        raise SystemExit("ERROR: no dated rows found in inputs")
    asof = parse_date(args.asof) if args.asof else max(all_dates)

    wk, wkp = weekly_windows(asof)
    mo, mop = monthly_windows(asof, args.month_mode)

    # --- watchlists ---
    target_urls, keywords = [], []
    if args.targets_file:
        u, k = load_targets_file(args.targets_file)
        target_urls += u
        keywords += k
    keywords += args.target_keywords.split(",")
    keywords = dedupe([k.strip() for k in keywords if k.strip()])
    target_urls = dedupe([u.strip() for u in target_urls if u.strip()])
    if target_urls and not page_rows:
        raise SystemExit("ERROR: target URLs require a --page-file (dimensions page,date)")

    # --- overall (ad-hoc focus optional) ---
    focus = {"applied": False}
    if args.query_filter:
        rows = filter_rows(query_rows, "query", args.query_filter)
        focus = {"applied": True, "type": "query", "pattern": args.query_filter,
                 "matched_queries": len({r["query"] for r in rows})}
        headline_rows = rows
    elif args.page_filter:
        if not page_rows:
            raise SystemExit("ERROR: --page-filter needs --page-file")
        rows = filter_rows(page_rows, "page", args.page_filter)
        focus = {"applied": True, "type": "page", "pattern": args.page_filter,
                 "matched_pages": len({r["page"] for r in rows})}
        headline_rows = rows
    else:
        headline_rows = date_rows

    overall = {"weekly": window_block(headline_rows, wk, wkp),
               "monthly": window_block(headline_rows, mo, mop)}

    url_report = track_targets(page_rows, "page", target_urls, norm_url,
                               wk, wkp, mo, mop) if target_urls else []
    kw_report = track_targets(query_rows, "query", keywords, norm_query,
                              wk, wkp, mo, mop, first_page=True)

    report = {
        "meta": {
            "client": args.client, "property": args.property, "asof": asof.isoformat(),
            "month_mode": args.month_mode, "focus": focus,
            "target_url_count": len(target_urls), "target_keyword_count": len(keywords),
            "note": "GSC lags ~2-3 days; 'asof' is the latest date available. Position is "
                    "impression-weighted; CTR is clicks/impressions per window. Query- and "
                    "URL-level numbers exclude GSC's anonymized (rare) queries, so they can "
                    "undercount vs the overall (date) totals.",
        },
        "overall": overall,
        "target_urls": url_report,
        "target_keywords": kw_report,
        "movers": {
            "by_query": movers(query_rows, "query", mo, mop, args.top),
            "by_page": movers(page_rows, "page", mo, mop, args.top) if page_rows else None,
        },
    }

    out = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    stem = os.path.splitext(out)[0]
    write_windows_csv(stem + "_windows.csv", overall)
    if kw_report:
        write_targets_csv(stem + "_target-keywords.csv", "query", kw_report, first_page=True)
    if url_report:
        write_targets_csv(stem + "_target-urls.csv", "page", url_report, first_page=False)
    write_movers_csv(stem + "_movers-query.csv", "query", report["movers"]["by_query"])
    if report["movers"]["by_page"]:
        write_movers_csv(stem + "_movers-page.csv", "page", report["movers"]["by_page"])

    # ---- stdout ----
    def ps(x):
        return f"{x:+.1f}%" if x is not None else "n/a"

    print(f"Traffic analysis — {args.property or args.client} — asof {asof}")
    if focus["applied"]:
        print(f"  OVERALL focus: {focus['type']} ~ /{focus['pattern']}/")
    for name in ("weekly", "monthly"):
        c, p, d = overall[name]["current"], overall[name]["previous"], overall[name]["delta"]
        print(f"\nOVERALL {name.upper()}: {c['label']} ({c['from']}..{c['to']}) vs {p['label']}")
        print(f"  clicks       {c['clicks']:>8} vs {p['clicks']:>8}  ({ps(d['clicks']['pct'])})")
        print(f"  impressions  {c['impressions']:>8} vs {p['impressions']:>8}  ({ps(d['impressions']['pct'])})")
        arrow = "improved" if d['position']['improved'] else "declined"
        print(f"  avg position {c['position']:>8} vs {p['position']:>8}  ({arrow} {abs(d['position']['abs'])})")

    if url_report:
        print(f"\nTARGET URLs ({len(url_report)}) — weekly clicks / position:")
        for t in url_report:
            wc = t["weekly"]["current"]
            if wc:
                print(f"  {t['page'][len('https://www.firstpage.hk'):] or '/':<62} "
                      f"clk {wc['clicks']:>4} ({t['weekly']['clicks_delta']:+d})  pos {wc['position']}")
            else:
                print(f"  {t['page'][len('https://www.firstpage.hk'):] or '/':<62} no impressions in window")

    if kw_report:
        print(f"\nTARGET QUERIES ({len(kw_report)}) — weekly position:")
        for t in kw_report:
            wc = t["weekly"]["current"]
            pos = wc["position"] if wc else "—"
            mv = f"({t['weekly']['position_movement']:+.1f})" if t["weekly"]["position_movement"] is not None else ""
            fp = "P1" if t["first_page"] else ""
            print(f"  {t['query']:<28} pos {str(pos):>5} {mv:>7} {fp}")

    print(f"\nWrote {out} (+ CSVs)")


if __name__ == "__main__":
    main()
