"""Prepare verified release packages and hand installation to a detached helper."""

import ctypes
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import plistlib
import re
import subprocess
import sys
import time
import urllib.request
import zipfile

from kirstgrab_platform import clean_subprocess_environment, find_macos_app_in_tree


MACOS_BUNDLE_IDENTIFIER = "com.polykek2k.kirstgrab"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def release_sha256(asset):
    digest = asset.get("digest")
    if isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest, re.IGNORECASE):
        return digest[7:].lower()
    return None


def download_release_archive(url, destination, expected_digest, progress):
    hasher = hashlib.sha256()
    downloaded = 0
    with urllib.request.urlopen(url, timeout=30) as response, destination.open("wb") as file:
        total = int(response.headers.get("Content-Length", "0"))
        while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
            file.write(chunk)
            hasher.update(chunk)
            downloaded += len(chunk)
            if total > 0:
                progress(min(100, 100 * downloaded / total))

    if hasher.hexdigest() != expected_digest:
        raise ValueError("Downloaded update failed SHA-256 verification")


def extract_release_archive(archive_path, destination):
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or PureWindowsPath(member.filename).drive:
                raise ValueError(f"Invalid path in update archive: {member.filename}")
        if sys.platform != "darwin":
            archive.extractall(destination)
            return

    # ditto preserves the symlinks and resource metadata in a signed app bundle.
    subprocess.run(
        ["/usr/bin/ditto", "-x", "-k", archive_path, destination],
        check=True,
        capture_output=True,
        text=True,
        env=clean_subprocess_environment(),
    )


def macos_codesign_team_identifier(app_path):
    result = subprocess.run(
        ["/usr/bin/codesign", "-dv", "--verbose=4", app_path],
        check=True,
        capture_output=True,
        text=True,
        env=clean_subprocess_environment(),
    )
    details = "\n".join((result.stdout, result.stderr))
    match = re.search(r"^TeamIdentifier=(.*)$", details, flags=re.MULTILINE)
    team = match.group(1).strip() if match else ""
    return None if team.lower() in {"", "not set"} else team


def find_update_payload(directory, destination, release_tag):
    if sys.platform.startswith("win"):
        matches = [
            path for path in directory.rglob("*")
            if path.is_file() and path.name.lower() == "kirstgrab.exe"
        ]
        if len(matches) != 1:
            raise ValueError("The release package must contain one KirstGrab.exe")
        return matches[0]

    app_path = find_macos_app_in_tree(directory)
    if app_path is None:
        raise ValueError("Could not find KirstGrab.app in the release package")
    source = Path(app_path)
    with (source / "Contents" / "Info.plist").open("rb") as file:
        info = plistlib.load(file)
    if info.get("CFBundleIdentifier") != MACOS_BUNDLE_IDENTIFIER:
        raise ValueError("The update has an unexpected app bundle identifier")

    expected_version = str(release_tag).removeprefix("v")
    source_version = str(info.get("CFBundleShortVersionString", "")).removeprefix("v")
    if source_version != expected_version:
        raise ValueError(f"Update bundle version {source_version!r} does not match {expected_version!r}")

    for bundle in (source, destination):
        subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", bundle],
            check=True,
            capture_output=True,
            text=True,
            env=clean_subprocess_environment(),
        )
    installed_team = macos_codesign_team_identifier(destination)
    if installed_team and macos_codesign_team_identifier(source) != installed_team:
        raise ValueError("The update is signed by a different Apple Developer team")
    return source


def launch_windows_helper(command, options):
    # PyInstaller's DLL directory is inherited by system programs launched here.
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        try:
            return subprocess.Popen(
                command,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_BREAKAWAY_FROM_JOB,
                **options,
            )
        except OSError as launch_error:
            # A job may forbid breaking away. Ask the system process provider
            # to start the same command outside that job.
            broker_options = dict(options, env={
                **options["env"],
                "KIRSTGRAB_UPDATER_COMMAND": subprocess.list2cmdline(command),
            })
            try:
                subprocess.run(
                    [command[0], "-NoProfile", "-NonInteractive", "-Command",
                     "$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
                     "-Arguments @{CommandLine=$env:KIRSTGRAB_UPDATER_COMMAND}; "
                     "if ($null -eq $result -or $result.ReturnValue -ne 0) { exit 1 }"],
                    check=True,
                    timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    **broker_options,
                )
            except (subprocess.SubprocessError, OSError) as broker_error:
                raise OSError(f"Could not start the detached updater ({launch_error}; {broker_error})") from broker_error
            return None
    finally:
        if bundle_root:
            ctypes.windll.kernel32.SetDllDirectoryW(bundle_root)


def launch_update_helper(work_dir, source, destination):
    """Return once the helper is ready to take over after the app exits."""
    log_path = work_dir.with_suffix(".log")
    options = {
        "cwd": work_dir.parent,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": clean_subprocess_environment(),
    }
    options["env"]["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if sys.platform.startswith("win"):
        # Windows PowerShell must not pick up modules from a running PowerShell 7.
        options["env"].pop("PSMODULEPATH", None)
        script = work_dir / "update.ps1"
        script.write_text(WINDOWS_UPDATER, encoding="utf-8")
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        command = [
            str(powershell), "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-File", str(script), str(os.getpid()),
            str(os.getppid()), str(source), str(destination), str(log_path),
        ]
        process = launch_windows_helper(command, options)
    else:
        script = work_dir / "update.sh"
        script.write_text(MACOS_UPDATER, encoding="utf-8", newline="\n")
        process = subprocess.Popen(
            ["/bin/sh", script, str(os.getpid()), source, destination, log_path],
            start_new_session=True,
            **options,
        )

    ready = work_dir / "ready"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            break
        if ready.is_file():
            (work_dir / "handoff").touch()
            return
        time.sleep(0.1)
    raise OSError(f"The updater did not get ready.\nLog: {log_path}")


WINDOWS_UPDATER = r"""param(
    [int]$AppId,
    [int]$ParentId,
    [string]$Source,
    [string]$Destination,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$destinationDir = [IO.Path]::GetDirectoryName($Destination)
$transaction = [IO.Path]::Combine($destinationDir, '.kirstgrab-update-' + [guid]::NewGuid())
$staged = [IO.Path]::Combine($transaction, 'new.exe')
$backup = [IO.Path]::Combine($transaction, 'previous.exe')
$handoff = [IO.Path]::Combine($PSScriptRoot, 'handoff')
$lock = $null
$appExited = $false
$committed = $false

function Write-UpdateLog([string]$Message) {
    try { [IO.File]::AppendAllText($LogPath, "$Message`r`n") } catch {}
}

function Start-KirstGrab {
    $info = [Diagnostics.ProcessStartInfo]::new($Destination)
    $info.WorkingDirectory = $destinationDir
    $info.UseShellExecute = $false
    $info.EnvironmentVariables['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return [Diagnostics.Process]::Start($info)
}

function Get-UpdateHash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return [Convert]::ToBase64String($sha256.ComputeHash($stream))
    } finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

try {
    Write-UpdateLog 'KirstGrab Windows update started'
    $lock = [IO.FileStream]::new(
        "$Destination.kirstgrab-lock", [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::None, 4096, [IO.FileOptions]::DeleteOnClose
    )
    $app = Get-Process -Id $AppId -ErrorAction SilentlyContinue
    $parent = Get-Process -Id $ParentId -ErrorAction SilentlyContinue
    if ($null -ne $parent -and $parent.Path -ne $Destination) { $parent = $null }
    [IO.File]::WriteAllText([IO.Path]::Combine($PSScriptRoot, 'ready'), '')

    if ($null -ne $app -and -not $app.WaitForExit(30000)) {
        throw 'Timed out waiting for KirstGrab to close'
    }
    # The one-file PyInstaller parent also keeps the executable open while it cleans up.
    if ($null -ne $parent -and -not $parent.WaitForExit(30000)) {
        throw 'Timed out waiting for the KirstGrab bootloader to exit'
    }
    if (-not [IO.File]::Exists($handoff)) { throw 'KirstGrab did not confirm the update' }
    $appExited = $true

    [void][IO.Directory]::CreateDirectory($transaction)
    [IO.File]::Copy($Source, $staged)
    if ((Get-UpdateHash $Source) -cne (Get-UpdateHash $staged)) {
        throw 'Staged executable failed SHA-256 verification'
    }

    for ($attempt = 1; ; $attempt++) {
        try {
            [IO.File]::Move($Destination, $backup)
            break
        } catch [System.IO.IOException], [System.UnauthorizedAccessException] {
            if ($attempt -ge 30 -or -not [IO.File]::Exists($Destination)) { throw }
            Start-Sleep -Milliseconds 500
        }
    }
    [IO.File]::Move($staged, $Destination)
    $updated = Start-KirstGrab
    try {
        if ($updated.WaitForExit(2000)) {
            throw "The updated application exited during startup (code $($updated.ExitCode))"
        }
    } finally {
        $updated.Dispose()
    }
    $committed = $true
    Write-UpdateLog 'Update completed successfully'
} catch {
    Write-UpdateLog "ERROR: $_"
    if ([IO.File]::Exists($backup)) {
        try {
            # If the staged file moved, the executable at Destination is the new one.
            if (-not [IO.File]::Exists($staged)) { [IO.File]::Delete($Destination) }
            [IO.File]::Move($backup, $Destination)
            Write-UpdateLog 'Previous executable restored'
        } catch {
            Write-UpdateLog "ERROR: Could not restore the executable. Backup: $backup. $_"
        }
    }
} finally {
    if ($committed -or -not [IO.File]::Exists($backup)) {
        Remove-Item -LiteralPath $transaction -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $lock) { $lock.Dispose() }
    $accepted = [IO.File]::Exists($handoff)
    if ($accepted) {
        Remove-Item -LiteralPath $PSScriptRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($committed) { exit 0 }
if ($appExited -and -not [IO.File]::Exists($backup) -and [IO.File]::Exists($Destination)) {
    try { (Start-KirstGrab).Dispose() } catch { Write-UpdateLog "ERROR: Could not reopen KirstGrab. $_" }
}
if ($accepted) {
    Add-Type -AssemblyName PresentationFramework
    [void][System.Windows.MessageBox]::Show("The KirstGrab update failed.`nLog: $LogPath", 'KirstGrab Update')
}
exit 1
"""


MACOS_UPDATER = r"""#!/bin/sh
set -u
umask 077
app_pid=$1
source=$2
destination=$3
log_file=$4
work_dir=${0%/*}
transaction="$destination.kirstgrab-update"
staged="$transaction/new.app"
backup="$transaction/previous.app"
locked=0
app_exited=0

log() {
    printf '%s\n' "$1" >> "$log_file"
}

restart_app() {
    /usr/bin/open -n "$destination" >> "$log_file" 2>&1
}

restore_bundle() {
    # If the staged app is still here, any app at the destination is not ours.
    if [ -e "$destination" ]; then
        [ ! -e "$staged" ] && /bin/mv "$destination" "$staged" || return 1
    fi
    /bin/mv "$backup" "$destination"
}

finish() {
    status=$?
    trap - EXIT HUP INT TERM
    if [ "$locked" = 1 ]; then
        if [ "$status" -ne 0 ] && [ -d "$backup" ]; then
            if restore_bundle; then
                log "Previous app bundle restored"
            else
                log "ERROR: Could not restore the app bundle. Backup: $backup"
            fi
        fi
        if [ "$status" -eq 0 ] || [ ! -d "$backup" ]; then
            /bin/rm -rf "$transaction"
        fi
    fi

    if [ -f "$work_dir/handoff" ]; then
        /bin/rm -rf "$work_dir"
        if [ "$status" -ne 0 ]; then
            if [ "$app_exited" = 1 ] && [ ! -d "$backup" ] && [ -d "$destination" ]; then
                restart_app || log "ERROR: Could not reopen KirstGrab"
            fi
            /usr/bin/osascript - "$log_file" >/dev/null 2>&1 <<'APPLESCRIPT'
on run argv
    display alert "KirstGrab update failed" message ("Log: " & item 1 of argv) as critical
end run
APPLESCRIPT
        fi
    fi
    exit "$status"
}

fail() {
    log "ERROR: $1"
    exit 1
}

trap finish EXIT
trap 'exit 1' HUP INT TERM
log "KirstGrab macOS update started"
/bin/mkdir "$transaction" || fail "Could not reserve the update directory: $transaction"
locked=1
: > "$work_dir/ready" || fail "Could not signal to KirstGrab"

attempt=0
while /bin/kill -0 "$app_pid" 2>/dev/null; do
    [ "$attempt" -lt 150 ] || fail "Timed out waiting for KirstGrab to close"
    attempt=$((attempt + 1))
    /bin/sleep 0.2
done
[ -f "$work_dir/handoff" ] || fail "KirstGrab did not confirm the update"
app_exited=1

/usr/bin/ditto "$source" "$staged" >> "$log_file" 2>&1 || fail "Could not stage the app bundle"
[ -x "$staged/Contents/MacOS/KirstGrab" ] || fail "The staged app has no executable"
/usr/bin/codesign --verify --deep --strict "$staged" >> "$log_file" 2>&1 || fail "Staged app signature verification failed"

/bin/mv "$destination" "$backup" || fail "Could not back up the installed app"
[ ! -e "$destination" ] || fail "The destination is occupied"
/bin/mv "$staged" "$destination" || fail "Could not install the staged app"
restart_app || fail "Could not launch the updated app"
log "Update completed successfully"
exit 0
"""
