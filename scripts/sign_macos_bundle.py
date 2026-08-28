#!/usr/bin/env python3
"""Sign KirstGrab.app and apply narrowly scoped entitlements to bundled tools."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def find_helper(app_path: Path, name: str) -> Path:
    matches = []
    for current_root, _directories, files in os.walk(app_path):
        if name not in files:
            continue
        candidate = Path(current_root) / name
        relative = candidate.relative_to(app_path).as_posix()
        if "/bin/" in f"/{relative}":
            matches.append(candidate)
    if not matches:
        raise RuntimeError(f"Bundled helper was not found: {name}")
    return sorted(matches, key=lambda path: len(path.parts))[0]


def codesign_command(
    identity: str,
    target: Path,
    entitlements: Path,
    *,
    deep: bool = False,
) -> list[str]:
    command = ["/usr/bin/codesign", "--force"]
    if deep:
        command.append("--deep")
    command.extend(["--sign", identity, "--options", "runtime"])
    if identity != "-":
        command.append("--timestamp")
    command.extend(["--entitlements", str(entitlements), str(target)])
    return command


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    parser.add_argument("--identity", required=True)
    parser.add_argument("--app-entitlements", required=True)
    parser.add_argument("--yt-dlp-entitlements", required=True)
    args = parser.parse_args()

    app_path = Path(args.app).resolve()
    app_entitlements = Path(args.app_entitlements).resolve()
    yt_dlp_entitlements = Path(args.yt_dlp_entitlements).resolve()
    for required_path in (app_path, app_entitlements, yt_dlp_entitlements):
        if not required_path.exists():
            raise RuntimeError(f"Required signing input was not found: {required_path}")

    yt_dlp = find_helper(app_path, "yt-dlp")
    deno = find_helper(app_path, "deno")

    # First normalize every nested signature. Then override the two executable
    # helpers with the minimum runtime exceptions they need and seal the outer
    # app again because changing nested code invalidates its resource envelope.
    run(codesign_command(args.identity, app_path, app_entitlements, deep=True))
    run(codesign_command(args.identity, yt_dlp, yt_dlp_entitlements))
    run(codesign_command(args.identity, deno, app_entitlements))
    run(codesign_command(args.identity, app_path, app_entitlements))
    run(
        [
            "/usr/bin/codesign",
            "--verify",
            "--deep",
            "--strict",
            "--verbose=2",
            str(app_path),
        ]
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"macOS bundle signing failed: {error}", file=sys.stderr)
        raise SystemExit(1)
