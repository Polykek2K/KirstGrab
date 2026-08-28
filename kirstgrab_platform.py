"""Platform-specific helpers for KirstGrab.

This module intentionally has no GUI imports so release selection and bundle
discovery can be tested on every operating system.
"""

from __future__ import annotations

import os
import ntpath
import platform as platform_module
import posixpath
import sys
import tempfile
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Optional


APP_NAME = "KirstGrab"


def normalize_architecture(machine: Optional[str] = None) -> str:
    value = (machine or platform_module.machine()).strip().lower()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "x86-64": "x86_64",
        "aarch64": "arm64",
    }
    return aliases.get(value, value or "unknown")


def platform_family(platform_name: Optional[str] = None) -> str:
    value = (platform_name or sys.platform).lower()
    if value.startswith("win"):
        return "windows"
    if value == "darwin":
        return "macos"
    if value.startswith("linux"):
        return "linux"
    return value


def clean_subprocess_environment(
    environ: Optional[Mapping[str, str]] = None,
    platform_name: Optional[str] = None,
    bundle_root: Optional[str] = None,
) -> dict[str, str]:
    """Return an environment safe for independent child processes.

    PyInstaller's private variables describe the current onefile process tree.
    Passing them through an external shell or to another frozen executable can
    make the new process look like a worker of the current executable and trip
    the bootloader's parent-process security validation.
    """

    environment = dict(os.environ if environ is None else environ)
    for variable in tuple(environment):
        if variable == "_MEIPASS2" or variable.startswith("_PYI_"):
            environment.pop(variable, None)

    active_bundle_root = getattr(sys, "_MEIPASS", None) if bundle_root is None else bundle_root
    if platform_family(platform_name) == "macos" and active_bundle_root:
        for variable in ("DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH"):
            entries = environment.get(variable, "").split(os.pathsep)
            entries = [
                entry
                for entry in entries
                if entry and not os.path.abspath(entry).startswith(active_bundle_root)
            ]
            if entries:
                environment[variable] = os.pathsep.join(entries)
            else:
                environment.pop(variable, None)

    return environment


def release_platform_key(
    platform_name: Optional[str] = None,
    machine: Optional[str] = None,
) -> str:
    return f"{platform_family(platform_name)}-{normalize_architecture(machine)}"


def executable_name(base_name: str, platform_name: Optional[str] = None) -> str:
    suffix = ".exe" if platform_family(platform_name) == "windows" else ""
    return f"{base_name}{suffix}"


def bundled_binary_paths(platform_name: Optional[str] = None) -> dict[str, str]:
    return {
        "yt_dlp": os.path.join("bin", executable_name("yt-dlp", platform_name)),
        "ffmpeg": os.path.join("bin", executable_name("ffmpeg", platform_name)),
        "ffprobe": os.path.join("bin", executable_name("ffprobe", platform_name)),
        "deno": os.path.join("bin", "deno", executable_name("deno", platform_name)),
    }


def select_release_asset(
    assets: Iterable[Mapping[str, object]],
    platform_name: Optional[str] = None,
    machine: Optional[str] = None,
) -> Optional[Mapping[str, object]]:
    """Select a release ZIP built for the current OS and architecture.

    Windows keeps accepting the historical ``release-<version>.zip`` name so
    existing releases remain installable. macOS deliberately requires an
    explicit platform suffix to avoid installing a Windows archive.
    """

    family = platform_family(platform_name)
    architecture = normalize_architecture(machine)
    candidates = []

    for asset in assets:
        name = str(asset.get("name", ""))
        lowered = name.lower()
        if lowered.endswith(".zip") and ("release" in lowered or "kirstgrab" in lowered):
            candidates.append((lowered, asset))

    exact_suffix = f"-{family}-{architecture}.zip"
    for name, asset in candidates:
        if name.endswith(exact_suffix):
            return asset

    if family == "macos":
        for name, asset in candidates:
            if name.endswith("-macos-universal2.zip"):
                return asset

    if family == "windows":
        platform_markers = ("-windows-", "-macos-", "-linux-")
        for name, asset in candidates:
            if not any(marker in name for marker in platform_markers):
                return asset

    return None


def user_data_directory(
    app_name: str = APP_NAME,
    platform_name: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
    home: Optional[str] = None,
) -> str:
    env = os.environ if environ is None else environ
    user_home = os.path.expanduser(home or "~")
    family = platform_family(platform_name)

    if family == "windows":
        base = env.get("APPDATA", ntpath.join(user_home, "AppData", "Roaming"))
        return ntpath.join(base, app_name)
    elif family == "macos":
        base = posixpath.join(user_home, "Library", "Application Support")
    else:
        base = env.get("XDG_DATA_HOME", posixpath.join(user_home, ".local", "share"))

    return posixpath.join(base, app_name)


def cookies_file_path(**kwargs: object) -> str:
    family = platform_family(kwargs.get("platform_name"))
    path_module = ntpath if family == "windows" else posixpath
    return path_module.join(user_data_directory(**kwargs), "cookies.txt")


def directory_is_writable(directory: str) -> bool:
    """Check real create/delete access instead of trusting permission bits alone."""

    probe_path = None
    try:
        descriptor, probe_path = tempfile.mkstemp(
            prefix=".kirstgrab-update-",
            dir=directory,
        )
        os.close(descriptor)
        os.unlink(probe_path)
        return True
    except OSError:
        if probe_path:
            try:
                os.unlink(probe_path)
            except OSError:
                pass
        return False


def macos_app_requires_manual_replacement(app_path: str) -> bool:
    """Return whether an app lives on a location that cannot be updated in place."""

    normalized = posixpath.normpath(app_path)
    lowered = normalized.lower()
    if "/apptranslocation/" in lowered:
        return True

    parent = posixpath.dirname(normalized)
    try:
        filesystem_flags = os.statvfs(parent).f_flag
    except (AttributeError, OSError):
        return False
    return bool(filesystem_flags & getattr(os, "ST_RDONLY", 1))


def find_macos_app_bundle(executable_path: str) -> Optional[str]:
    current = PurePosixPath(executable_path)
    for candidate in (current, *current.parents):
        if candidate.name.lower().endswith(".app"):
            return str(candidate)
    return None


def find_macos_app_in_tree(root: str, app_name: str = APP_NAME) -> Optional[str]:
    expected_name = f"{app_name}.app".lower()
    matches = []
    for current_root, directories, _files in os.walk(root):
        for directory in directories:
            if directory.lower() == expected_name:
                matches.append(os.path.join(current_root, directory))
        directories[:] = [d for d in directories if not d.lower().endswith(".app")]
    return sorted(matches)[0] if matches else None
