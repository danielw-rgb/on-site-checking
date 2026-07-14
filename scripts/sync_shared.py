#!/usr/bin/env python3
"""Keep the vendored `_shared/` copies in sync with their canonical sources.

Each standalone skill ships a copy of shared infrastructure inside its own
`_shared/` folder (materialised into the project by the skill's Step 0
bootstrap). The canonical source of truth lives in the shared project tree.
This script keeps the two byte-identical.

Usage:
    python3 scripts/sync_shared.py            # copy canonical -> every vendored copy
    python3 scripts/sync_shared.py --check    # report drift only; exit 1 if any

The pre-commit hook (.githooks/pre-commit) runs `--check` as a non-blocking
reminder so a connector/template edit doesn't ship with stale vendored copies.
"""
import filecmp
import glob
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# canonical source (relative to repo root)  ->  glob of vendored copies
# Extend this list when SF / Ahrefs skills gain vendored _shared bundles.
PAIRS = [
    ("gsc/connector/gsc_fetch.py",  ".claude/skills/*(GSC)/_shared/gsc_fetch.py"),
    ("gsc/requirements.txt",        ".claude/skills/*(GSC)/_shared/requirements.txt"),
    (".env.example",                ".claude/skills/*(GSC)/_shared/.env.example"),
    ("gsc/clients.example.json",    ".claude/skills/*(GSC)/_shared/clients.example.json"),
]


def resolve():
    """Yield (canonical_abs, vendored_abs) for every vendored copy on disk."""
    for src_rel, pat in PAIRS:
        src = os.path.join(ROOT, src_rel)
        for dst in glob.glob(os.path.join(ROOT, pat)):
            yield src, dst


def rel(p):
    return os.path.relpath(p, ROOT)


def main():
    check = "--check" in sys.argv[1:]
    drift, missing_src = [], []

    for src, dst in resolve():
        if not os.path.exists(src):
            missing_src.append(src)
            continue
        if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
            continue
        drift.append((src, dst))
        if not check:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    if check:
        if drift:
            print("[sync-shared] vendored _shared/ copies are OUT OF SYNC with canonical:")
            for src, dst in drift:
                print(f"  - {rel(dst)}  !=  {rel(src)}")
            print("  Fix:  python3 scripts/sync_shared.py   then re-stage the _shared files.")
        else:
            print("[sync-shared] all vendored copies in sync.")
    else:
        for src, dst in drift:
            print(f"synced  {rel(dst)}  <-  {rel(src)}")
        if not drift:
            print("[sync-shared] nothing to do; already in sync.")

    if missing_src:
        print("WARNING: canonical source(s) missing:",
              ", ".join(rel(p) for p in missing_src))

    if check and drift:
        sys.exit(1)


if __name__ == "__main__":
    main()
