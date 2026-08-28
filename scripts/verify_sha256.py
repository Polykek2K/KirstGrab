#!/usr/bin/env python3
"""Verify a downloaded file against a standard SHA-256 checksum list."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import re
import sys
from pathlib import Path


SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def expected_digest(checksum_text: str, entry_name: str | None = None) -> str:
    named_matches: list[str] = []
    unnamed_matches: list[str] = []
    named_entries_seen = False

    for line in checksum_text.splitlines():
        fields = line.strip().split()
        if not fields or not SHA256_PATTERN.fullmatch(fields[0]):
            continue

        digest = fields[0].lower()
        if len(fields) == 1:
            unnamed_matches.append(digest)
            continue

        named_entries_seen = True
        name = fields[-1].lstrip("*")
        if name.startswith("./"):
            name = name[2:]
        if entry_name is None or name == entry_name:
            named_matches.append(digest)

    matches = named_matches if named_entries_seen else unnamed_matches
    if len(matches) != 1:
        target = entry_name or "the requested file"
        raise ValueError(f"Expected exactly one SHA-256 checksum for {target}, found {len(matches)}")
    return matches[0]


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as downloaded_file:
        for chunk in iter(lambda: downloaded_file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_file(file_path: Path, checksum_path: Path, entry_name: str | None = None) -> str:
    expected = expected_digest(checksum_path.read_text(encoding="utf-8"), entry_name)
    actual = file_digest(file_path)
    if not hmac.compare_digest(actual, expected):
        raise ValueError(
            f"SHA-256 mismatch for {file_path.name}: expected {expected}, got {actual}"
        )
    return actual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("checksums", type=Path)
    parser.add_argument("--entry", help="Filename to select from a multi-entry checksum list")
    args = parser.parse_args()

    try:
        digest = verify_file(args.file, args.checksums, args.entry)
    except (OSError, ValueError) as error:
        print(f"SHA-256 verification failed: {error}", file=sys.stderr)
        return 1

    print(f"Verified SHA-256 for {args.file}: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
