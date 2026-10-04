#!/usr/bin/env python3
"""Fetch or verify the exact upstream Employees source files pinned by manifest.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


class SourceError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(destination: Path, source_directory: Path | None = None) -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    source = manifest["source"]
    repo = source["repository"].removesuffix(".git")
    if not repo.startswith("https://github.com/"):
        raise SourceError("source.repository must be a public GitHub HTTPS URL")
    raw_repo = repo.replace("https://github.com/", "https://raw.githubusercontent.com/", 1)
    revision = source["revision"]
    if len(revision) != 40 or any(ch not in "0123456789abcdef" for ch in revision):
        raise SourceError("source.revision must be a full lowercase commit SHA")

    destination.mkdir(parents=True, exist_ok=True)
    for item in source["recipe"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise SourceError(f"unsafe pinned source path: {relative}")
        local_name = relative.name
        target = destination / local_name
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=f".{local_name}.", dir=destination, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            try:
                if source_directory is not None:
                    candidate = source_directory / local_name
                    if not candidate.is_file():
                        raise SourceError(f"pinned source file is missing: {candidate}")
                    incoming = candidate.open("rb")
                else:
                    incoming = urlopen(f"{raw_repo}/{revision}/{relative.as_posix()}", timeout=60)
                with incoming:
                    for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                        temporary.write(chunk)
                        digest.update(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
        actual = digest.hexdigest()
        if actual != item["sha256"]:
            temporary_path.unlink(missing_ok=True)
            raise SourceError(f"SHA-256 mismatch for {relative}: expected {item['sha256']}, got {actual}")
        os.replace(temporary_path, target)
        print(f"verified {relative} ({item['sha256']})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True, help="directory for verified upstream files")
    parser.add_argument("--source-directory", type=Path, help="use already downloaded files instead of HTTP")
    args = parser.parse_args()
    fetch(args.destination.resolve(), args.source_directory.resolve() if args.source_directory else None)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError, SourceError) as error:
        raise SystemExit(f"error: {error}")
