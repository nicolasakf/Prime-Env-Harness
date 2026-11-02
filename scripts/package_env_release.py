#!/usr/bin/env python3
"""Package a prime-env-harness release archive.

Stages the exe-adjacent layout the binary resolves at runtime (the directory
of the executable, or PI_PACKAGE_DIR):

  prime-env-harness-<version>-<platform>/
    prime-env-harness      the binary (mode 755)
    package.json           {"version": <version>}
    README.md, LICENSE
    prime-agent-runtime/   the Python kernel sidecar (dev caches excluded)
    skills/                built-in skills
    docs/                  user-facing docs

and writes <out-dir>/prime-env-harness-<version>-<platform>.tar.gz plus a
.sha256 file beside it. Nothing is published or downloaded here; the release
workflow uploads the outputs.

Usage:
  scripts/package_env_release.py --binary target/release/prime-env-harness \
      --platform macos-arm64 --out-dir target/release/dist
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINARY_NAME = "prime-env-harness"
PLATFORMS = ("linux-x64", "linux-arm64", "macos-x64", "macos-arm64")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")

# Development caches never ship.
EXCLUDED_NAMES = {
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".git",
    ".DS_Store",
}
# The kernel sidecar additionally drops its tests and lockfile (they are not
# part of the runtime identity the bootstrap hashes).
RUNTIME_EXTRA_EXCLUDED = {"test", "uv.lock"}
EXCLUDED_SUFFIXES = (".pyc", ".egg-info")

TREE_ASSETS = ("prime-agent-runtime", "skills", "docs")
FILE_ASSETS = ("README.md", "LICENSE")
REQUIRED = (
    BINARY_NAME,
    "package.json",
    "README.md",
    "LICENSE",
    "prime-agent-runtime/pyproject.toml",
    "prime-agent-runtime/src/rlm/repl.py",
    "skills/environments/SKILL.md",
    "docs/harness.md",
)


def fail(message):
    print(f"package_env_release: {message}", file=sys.stderr)
    sys.exit(1)


def workspace_version():
    # The Linux build container ships Python 3.10, which has no tomllib.
    section = (ROOT / "Cargo.toml").read_text().split("[workspace.package]", 1)[1]
    section = section.split("\n[", 1)[0]
    return re.search(r'^version\s*=\s*"([^"]+)"', section, re.MULTILINE).group(1)


def copy_tree(source, target):
    excluded = EXCLUDED_NAMES | (RUNTIME_EXTRA_EXCLUDED if source.name == "prime-agent-runtime" else set())

    def ignore(_directory, names):
        return [name for name in names if name in excluded or name.endswith(EXCLUDED_SUFFIXES)]

    shutil.copytree(source, target, ignore=ignore)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--version", help="default: the workspace version")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    version = args.version or workspace_version()
    if not VERSION_RE.match(version):
        fail(f"invalid version {version!r}")
    if not args.binary.is_file():
        fail(f"binary not found: {args.binary}")

    name = f"{BINARY_NAME}-{version}-{args.platform}"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    staging = args.out_dir / name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()

    shutil.copy2(args.binary, staging / BINARY_NAME)
    (staging / BINARY_NAME).chmod(0o755)
    (staging / "package.json").write_text(json.dumps({"version": version}) + "\n")
    for asset in FILE_ASSETS:
        shutil.copy2(ROOT / asset, staging / asset)
    for asset in TREE_ASSETS:
        copy_tree(ROOT / asset, staging / asset)

    missing = [entry for entry in REQUIRED if not (staging / entry).exists()]
    if missing:
        fail(f"staged tree is missing: {', '.join(missing)}")

    archive = args.out_dir / f"{name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(staging.rglob("*")):
            info = tar.gettarinfo(str(path), arcname=f"{name}/{path.relative_to(staging)}")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            if path.is_file():
                with path.open("rb") as handle:
                    tar.addfile(info, handle)
            else:
                tar.addfile(info)
    shutil.rmtree(staging)

    checksum = sha256_file(archive)
    (args.out_dir / f"{archive.name}.sha256").write_text(f"{checksum}  {archive.name}\n")
    print(f"{archive} {checksum}")


main()
