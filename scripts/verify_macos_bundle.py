#!/usr/bin/env python3
"""Validate a built KirstGrab.app and its bundled command-line helpers."""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path


HELPERS = {
    "yt-dlp": ["--version"],
    "ffmpeg": ["-version"],
    "ffprobe": ["-version"],
    "deno": ["eval", "console.log(1 + 1)"],
}


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command))
    return subprocess.run(command, check=True, text=True, **kwargs)


def find_helper(app_path: Path, name: str) -> Path:
    matches = []
    for current_root, _directories, files in os.walk(app_path):
        if name in files:
            candidate = Path(current_root) / name
            relative = candidate.relative_to(app_path).as_posix()
            if "/bin/" in f"/{relative}":
                matches.append(candidate)
    if not matches:
        raise RuntimeError(f"Bundled helper was not found: {name}")
    return sorted(matches, key=lambda path: len(path.parts))[0]


def ensure_path_within_bundle(app_path: Path, candidate: Path) -> None:
    bundle_root = app_path.resolve()
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(bundle_root)
    except ValueError as error:
        raise RuntimeError(
            f"Bundle symlink escapes KirstGrab.app: {candidate} -> {resolved_candidate}"
        ) from error


def is_macho(path: Path) -> bool:
    result = subprocess.run(
        ["/usr/bin/file", "-b", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return "Mach-O" in result.stdout


def verify_linkage(binary: Path) -> None:
    result = run(["/usr/bin/otool", "-L", str(binary)], capture_output=True)
    allowed_absolute_dependencies = (
        "/System/Library/",
        "/usr/lib/",
        "/Library/Apple/System/Library/",
    )
    for line in result.stdout.splitlines()[1:]:
        dependency = line.strip().split(" ", 1)[0]
        if not (
            dependency.startswith("@")
            or dependency.startswith(allowed_absolute_dependencies)
        ):
            raise RuntimeError(f"Non-portable dependency in {binary}: {dependency}")

    load_commands = run(["/usr/bin/otool", "-l", str(binary)], capture_output=True).stdout.splitlines()
    for index, line in enumerate(load_commands):
        if line.strip() != "cmd LC_RPATH":
            continue
        for detail in load_commands[index + 1:index + 5]:
            detail = detail.strip()
            if not detail.startswith("path "):
                continue
            rpath = detail.split(" ", 2)[1]
            if not (rpath.startswith("@") or rpath.startswith(allowed_absolute_dependencies)):
                raise RuntimeError(f"Non-portable LC_RPATH in {binary}: {rpath}")
            break


def verify_all_macho_files(app_path: Path, architecture: str) -> None:
    macho_count = 0
    for candidate in app_path.rglob("*"):
        if candidate.is_symlink():
            ensure_path_within_bundle(app_path, candidate)
            continue
        if not candidate.is_file() or not is_macho(candidate):
            continue

        macho_count += 1
        architectures = run(
            ["/usr/bin/lipo", "-archs", str(candidate)],
            capture_output=True,
        ).stdout.strip().split()
        if architecture not in architectures:
            raise RuntimeError(
                f"Mach-O file does not contain {architecture}: {candidate} ({architectures})"
            )
        verify_linkage(candidate)

    if macho_count == 0:
        raise RuntimeError("KirstGrab.app contains no Mach-O files")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    parser.add_argument("--architecture", required=True, choices=("arm64", "x86_64"))
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    app_path = Path(args.app).resolve()
    info_plist = app_path / "Contents" / "Info.plist"
    if not info_plist.is_file():
        raise RuntimeError(f"Info.plist was not found in {app_path}")

    with info_plist.open("rb") as plist_file:
        info = plistlib.load(plist_file)
    if info.get("CFBundleIdentifier") != "com.polykek2k.kirstgrab":
        raise RuntimeError("Unexpected CFBundleIdentifier")
    if info.get("CFBundleShortVersionString") != args.version:
        raise RuntimeError("Unexpected CFBundleShortVersionString")

    for required_document in ("LICENSE", "THIRD_PARTY_NOTICES.md", "BUILD-MANIFEST.txt"):
        if not any(path.is_file() for path in app_path.rglob(required_document)):
            raise RuntimeError(f"Required bundled document is missing: {required_document}")

    run(["/usr/bin/plutil", "-lint", str(info_plist)])

    verify_all_macho_files(app_path, args.architecture)

    main_executable = app_path / "Contents" / "MacOS" / "KirstGrab"
    main_architecture = run(
        ["/usr/bin/lipo", "-archs", str(main_executable)],
        capture_output=True,
    ).stdout.strip().split()
    if args.architecture not in main_architecture:
        raise RuntimeError(f"Main executable does not contain {args.architecture}")

    resolved_helpers = {}
    for helper_name, version_args in HELPERS.items():
        helper = find_helper(app_path, helper_name)
        resolved_helpers[helper_name] = helper
        if not os.access(helper, os.X_OK):
            raise RuntimeError(f"Bundled helper is not executable: {helper}")

        architecture_result = run(["/usr/bin/lipo", "-archs", str(helper)], capture_output=True)
        architectures = architecture_result.stdout.strip().split()
        if args.architecture not in architectures:
            raise RuntimeError(
                f"{helper_name} does not contain {args.architecture}: {architectures}"
            )

        run([str(helper), *version_args], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    with tempfile.TemporaryDirectory(prefix="KirstGrab-ffmpeg-test-") as temp_directory:
        mp3_path = Path(temp_directory) / "smoke-test.mp3"
        run(
            [
                str(resolved_helpers["ffmpeg"]),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-t",
                "0.1",
                "-codec:a",
                "libmp3lame",
                "-y",
                str(mp3_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        run(
            [str(resolved_helpers["ffprobe"]), "-v", "error", str(mp3_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

    self_test_environment = os.environ.copy()
    self_test_environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    run(
        [str(main_executable), "--self-test"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        env=self_test_environment,
    )

    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_path)])
    print(f"Verified {app_path} for macOS {args.architecture}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"macOS bundle verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
