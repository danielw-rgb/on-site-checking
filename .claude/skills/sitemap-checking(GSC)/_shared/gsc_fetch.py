#!/usr/bin/env python3
"""GSC connector — reusable auth + Search Analytics fetch for the Onsite Checking Workflow.

OAuth (installed-app) multi-account model: ONE OAuth client (your app) is consented
once per agency Google account. Each account's refresh token is cached so you do NOT
re-login every run. When handling a client, pick the account slug that has GSC access
to that client's property.

One-time per agency Google account (opens a browser to consent):
    python gsc/connector/gsc_fetch.py auth --account agency1

Pull Search Analytics rows for a client property:
    python gsc/connector/gsc_fetch.py query \
        --account agency1 \
        --property sc-domain:example.com \
        --dimensions query,page \
        --date-from 2026-03-01 --date-to 2026-05-31 \
        --output gsc/keyword-cannibalization/data/example-com/2026-06-30.ndjson

Or resolve account + property from gsc/clients.json by slug:
    python gsc/connector/gsc_fetch.py query --client example-client \
        --dimensions query,page --date-from 2026-03-01 --date-to 2026-05-31 \
        --output gsc/keyword-cannibalization/data/example-com/2026-06-30.ndjson

Credentials come from the repo-root .env (GSC_OAUTH_CLIENT_ID / GSC_OAUTH_CLIENT_SECRET,
or GSC_OAUTH_CLIENT_SECRET_FILE). Requires: google-api-python-client, google-auth,
google-auth-oauthlib  (see gsc/requirements.txt).
"""
import argparse
import json
import os
import sys
from collections import OrderedDict

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
ROW_LIMIT = 25000  # GSC Search Analytics API max rows per request


def repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def abspath(p):
    return p if os.path.isabs(p) else os.path.join(repo_root(), p)


def load_env(path=None):
    """Minimal .env parser (no external dependency)."""
    path = abspath(path) if path else os.path.join(repo_root(), ".env")
    env = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def client_config(env):
    """Return (config_dict, secret_file_path) — exactly one is non-None."""
    cid = env.get("GSC_OAUTH_CLIENT_ID")
    csecret = env.get("GSC_OAUTH_CLIENT_SECRET")
    secret_file = env.get("GSC_OAUTH_CLIENT_SECRET_FILE")
    if cid and csecret:
        return {
            "installed": {
                "client_id": cid,
                "client_secret": csecret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }, None
    if secret_file:
        return None, abspath(secret_file)
    sys.exit(
        "ERROR: set GSC_OAUTH_CLIENT_ID + GSC_OAUTH_CLIENT_SECRET "
        "(or GSC_OAUTH_CLIENT_SECRET_FILE) in .env"
    )


def token_path(env, account):
    if not account:
        sys.exit("ERROR: no --account given and GSC_DEFAULT_ACCOUNT is unset in .env")
    tdir = abspath(env.get("GSC_TOKEN_DIR", "gsc/credentials"))
    os.makedirs(tdir, exist_ok=True)
    return os.path.join(tdir, f"token_{account}.json")


def load_clients(env):
    p = os.path.join(repo_root(), "gsc", "clients.json")
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


def do_auth(env, account):
    from google_auth_oauthlib.flow import InstalledAppFlow

    cfg, secret_file = client_config(env)
    if cfg:
        flow = InstalledAppFlow.from_client_config(cfg, SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    tp = token_path(env, account)
    with open(tp, "w") as f:
        f.write(creds.to_json())
    print(f"Saved token for account '{account}' -> {tp}")


def load_creds(env, account):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    tp = token_path(env, account)
    if not os.path.exists(tp):
        sys.exit(
            f"ERROR: no token for account '{account}'. Run:\n"
            f"  python gsc/connector/gsc_fetch.py auth --account {account}"
        )
    creds = Credentials.from_authorized_user_file(tp, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(tp, "w") as f:
                f.write(creds.to_json())
        else:
            sys.exit(f"ERROR: token for '{account}' is invalid; re-run auth.")
    return creds


def do_query(env, args):
    from googleapiclient.discovery import build

    # Resolve account + property from the client registry if --client was given.
    if args.client:
        entry = load_clients(env).get(args.client)
        if not entry:
            sys.exit(f"ERROR: client '{args.client}' not found in gsc/clients.json")
        args.account = args.account or entry.get("account")
        args.property = args.property or entry.get("property")
    if not args.account:
        args.account = env.get("GSC_DEFAULT_ACCOUNT")
    if not args.property:
        sys.exit("ERROR: --property (or --client) is required")

    creds = load_creds(env, args.account)
    service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    dims = [d.strip() for d in args.dimensions.split(",") if d.strip()]

    rows_out = []
    start = 0
    while True:
        body = {
            "startDate": args.date_from,
            "endDate": args.date_to,
            "dimensions": dims,
            "rowLimit": ROW_LIMIT,
            "startRow": start,
            "type": args.search_type,
        }
        resp = service.searchanalytics().query(siteUrl=args.property, body=body).execute()
        rows = resp.get("rows", [])
        for r in rows:
            keys = r.get("keys", [])
            rec = OrderedDict((dims[i], keys[i]) for i in range(len(dims)))
            rec["clicks"] = r.get("clicks", 0)
            rec["impressions"] = r.get("impressions", 0)
            rec["ctr"] = r.get("ctr", 0)
            rec["position"] = r.get("position", 0)
            rows_out.append(rec)
        if len(rows) < ROW_LIMIT:
            break
        start += ROW_LIMIT

    out = abspath(args.output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        for rec in rows_out:
            f.write(json.dumps(rec) + "\n")
    print(f"Wrote {len(rows_out)} rows -> {out}")
    print(
        f"  property={args.property} account={args.account} "
        f"dims={dims} {args.date_from}..{args.date_to} type={args.search_type}"
    )


def main():
    p = argparse.ArgumentParser(description="GSC connector (OAuth multi-account)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("auth", help="One-time browser consent for an agency Google account")
    pa.add_argument("--account", required=True, help="Account slug, e.g. agency1")
    pa.add_argument("--env", help="Path to .env (default: repo-root .env)")

    pq = sub.add_parser("query", help="Fetch Search Analytics rows to NDJSON")
    pq.add_argument("--client", help="Slug in gsc/clients.json (fills account + property)")
    pq.add_argument("--account", help="Account slug (overrides client/env default)")
    pq.add_argument("--property", help="sc-domain:example.com or https://www.example.com/")
    pq.add_argument("--dimensions", default="query,page", help="Comma-separated (default query,page)")
    pq.add_argument("--date-from", required=True, dest="date_from")
    pq.add_argument("--date-to", required=True, dest="date_to")
    pq.add_argument("--search-type", default="web", dest="search_type", help="web|image|video|news|discover")
    pq.add_argument("--output", required=True, help="Output NDJSON path")
    pq.add_argument("--env", help="Path to .env (default: repo-root .env)")

    args = p.parse_args()
    env = load_env(getattr(args, "env", None))
    if args.cmd == "auth":
        do_auth(env, args.account)
    elif args.cmd == "query":
        do_query(env, args)


if __name__ == "__main__":
    main()
