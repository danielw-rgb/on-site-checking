#!/usr/bin/env python3
"""Bootstrap the shared GSC workspace for a standalone (GSC) skill.

Every (GSC) skill ships a self-contained copy of the connector + templates in
its own `_shared/` folder. This script materialises them into the SHARED project
tree — `gsc/connector/gsc_fetch.py`, `gsc/requirements.txt`, `.env`,
`gsc/clients.example.json`, `gsc/credentials/` — but only for pieces that do not
already exist. So installing several (GSC) skills into one project yields a
single shared connector + credentials store, not one copy per skill.

Run from the project root (skills are always invoked from there):

    python3 ".claude/skills/<skill>(GSC)/_shared/bootstrap.py"

Pass `--project-root <dir>` to target a different root. Idempotent: safe to run
repeatedly; existing files are left untouched.

Note: the connector MUST live at `gsc/connector/gsc_fetch.py` — it resolves the
project root, `.env`, `gsc/credentials/`, and `gsc/clients.json` relative to its
own location (two levels up). Running it from anywhere else breaks those paths.
"""
import os
import shutil
import sys

SRC = os.path.dirname(os.path.abspath(__file__))  # .../<skill>(GSC)/_shared


def project_root():
    """Where to install the shared workspace. Defaults to the current working
    directory (all skill commands run from the project root)."""
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == "--project-root" and i + 1 < len(argv):
            return os.path.abspath(argv[i + 1])
    return os.getcwd()


def copy_if_absent(src, dst, created, skipped):
    if os.path.exists(dst):
        skipped.append(dst)
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    created.append(dst)


def env_has_client(path):
    """True if .env already carries a non-empty OAuth client id."""
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("GSC_OAUTH_CLIENT_ID=") and line.split("=", 1)[1]:
                    return True
    except OSError:
        return False
    return False


def main():
    root = project_root()
    created, skipped = [], []

    # 1. Shared connector -> gsc/connector/gsc_fetch.py (must be at this path)
    copy_if_absent(os.path.join(SRC, "gsc_fetch.py"),
                   os.path.join(root, "gsc", "connector", "gsc_fetch.py"),
                   created, skipped)
    # 2. Dependency list -> gsc/requirements.txt
    copy_if_absent(os.path.join(SRC, "requirements.txt"),
                   os.path.join(root, "gsc", "requirements.txt"),
                   created, skipped)
    # 3. Secrets template -> .env (only when the project has no .env yet)
    copy_if_absent(os.path.join(SRC, ".env.example"),
                   os.path.join(root, ".env"),
                   created, skipped)
    # 4. Client registry template -> gsc/clients.example.json
    copy_if_absent(os.path.join(SRC, "clients.example.json"),
                   os.path.join(root, "gsc", "clients.example.json"),
                   created, skipped)
    # 5. Credentials dir (per-account tokens are written here on first auth)
    cred = os.path.join(root, "gsc", "credentials")
    if os.path.isdir(cred):
        skipped.append(cred + os.sep)
    else:
        os.makedirs(cred, exist_ok=True)
        created.append(cred + os.sep)

    def rel(p):
        return os.path.relpath(p, root)

    print("GSC workspace bootstrap - project root:", root)
    if created:
        print("  created:")
        for p in created:
            print("   +", rel(p))
    if skipped:
        print("  already present (left as-is):")
        for p in skipped:
            print("   =", rel(p))

    print()
    print("Next steps:")
    if env_has_client(os.path.join(root, ".env")):
        print("  1. .env already has an OAuth client - ok")
    else:
        print("  1. Fill GSC_OAUTH_CLIENT_ID / GSC_OAUTH_CLIENT_SECRET in .env")
    print("  2. pip install -r gsc/requirements.txt")
    print("  3. python3 gsc/connector/gsc_fetch.py auth --account <slug>")


if __name__ == "__main__":
    main()
