#!/usr/bin/env python3
"""Before/after file inventory for Codex write runs.

See docs/agent-collaboration.md section 4. `git status` cannot see edits to
ignored files such as CLAUDE.local.md or .env, so this records every file in
the checkout except the regenerable directories listed below. It also records
HEAD, the index (`git ls-files --stage`), and `git status`, so staging or
committing without changing file contents is still reported.

Usage:
    inventory.py snapshot --root <repo> --out <file.json>
    inventory.py diff <before.json> <after.json>
"""

import argparse
import fnmatch
import hashlib
import json
import os
import stat
import subprocess  # nosec B404
import sys

# Regenerable or tool-owned directories, matched by name at any depth.
EXCLUDED_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".vite",
    "htmlcov",
    ".superpowers",  # Claude's local records, written during runs
}
# Regenerable directories, matched by path relative to the root.
EXCLUDED_REL_DIRS = {"frontend/dist"}
# Regenerable files, matched by basename.
EXCLUDED_FILE_GLOBS = [".coverage", ".coverage.*", ".DS_Store"]


def _entry(path):
    info = os.lstat(path)
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        return {"type": "symlink", "mode": oct(mode), "target": os.readlink(path)}
    if stat.S_ISREG(info.st_mode):
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return {
            "type": "file",
            "mode": oct(mode),
            "size": info.st_size,
            "sha256": digest.hexdigest(),
        }
    return {"type": "other", "mode": oct(mode)}


def _git(root, *args):
    """Run a fixed read-only git command without a shell; None on failure."""
    try:
        out = subprocess.run(  # nosec B603 B607
            ["git", "-C", root, *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout


def snapshot(root):
    root = os.path.abspath(root)
    files = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        kept = []
        for name in sorted(dirnames):
            rel = os.path.normpath(os.path.join(rel_dir, name))
            full = os.path.join(dirpath, name)
            if name in EXCLUDED_DIR_NAMES or rel in EXCLUDED_REL_DIRS:
                continue
            if os.path.islink(full):
                files[rel] = _entry(full)  # record the link; do not descend
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            if any(fnmatch.fnmatch(name, pat) for pat in EXCLUDED_FILE_GLOBS):
                continue
            rel = os.path.normpath(os.path.join(rel_dir, name))
            files[rel] = _entry(os.path.join(dirpath, name))
    return {
        "root": root,
        "head": (_git(root, "rev-parse", "HEAD") or "").strip(),
        "index_sha256": hashlib.sha256(
            (_git(root, "ls-files", "--stage") or "").encode("utf-8")
        ).hexdigest(),
        "git_status": _git(root, "status", "--porcelain=v1", "--untracked-files=all"),
        "excluded": {
            "dir_names": sorted(EXCLUDED_DIR_NAMES),
            "rel_dirs": sorted(EXCLUDED_REL_DIRS),
            "file_globs": EXCLUDED_FILE_GLOBS,
        },
        "files": files,
    }


def diff(before, after):
    old, new = before["files"], after["files"]
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = []
    for path in sorted(set(old) & set(new)):
        a, b = old[path], new[path]
        if a == b:
            continue
        what = [
            key
            for key in ("type", "mode", "target", "size", "sha256")
            if a.get(key) != b.get(key)
        ]
        changed.append((path, what))
    return added, removed, changed


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--root", required=True)
    snap.add_argument("--out", required=True)
    cmp_ = sub.add_parser("diff")
    cmp_.add_argument("before")
    cmp_.add_argument("after")
    args = parser.parse_args(argv)

    if args.cmd == "snapshot":
        data = snapshot(args.root)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
        print(
            f"{len(data['files'])} files recorded at HEAD {data['head'][:12] or '?'} -> {args.out}"
        )
        return 0

    with open(args.before, encoding="utf-8") as fh:
        before = json.load(fh)
    with open(args.after, encoding="utf-8") as fh:
        after = json.load(fh)
    if before["head"] != after["head"]:
        print(f"GIT: HEAD moved {before['head'][:12]} -> {after['head'][:12]}")
    if before.get("index_sha256") != after.get("index_sha256"):
        print("GIT: index changed (something was staged or unstaged)")
    old_status = set((before.get("git_status") or "").splitlines())
    new_status = set((after.get("git_status") or "").splitlines())
    for line in sorted(new_status - old_status):
        print(f"status+   {line}")
    for line in sorted(old_status - new_status):
        print(f"status-   {line}")
    added, removed, changed = diff(before, after)
    for path in added:
        print(f"added     {path}")
    for path in removed:
        print(f"deleted   {path}")
    for path, what in changed:
        print(f"modified  {path}  ({', '.join(what)})")
    print(
        f"summary: {len(added)} added, {len(removed)} deleted, {len(changed)} modified"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
