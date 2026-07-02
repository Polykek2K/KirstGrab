#requires -Version 5.1
<#
.SYNOPSIS
Builds dist\KirstGrab.exe locally using the same inputs as GitHub Actions.

.EXAMPLE
.\build-local.ps1
Downloads fresh build inputs and creates dist\KirstGrab.exe.

.EXAMPLE
.\build-local.ps1 -SkipDownload
Reuses existing yt-dlp.exe, ffmpeg\, and deno\ inputs for a faster rebuild.

.EXAMPLE
.\build-local.ps1 -Python C:\Users\anton\AppData\Local\Programs\Python\Python312\python.exe
Uses an explicit Python executable. The Python installation must include tkinter.
#>
[CmdletBinding()]
param(
    [string]$Python,
    [switch]$SkipDownload,
    [switch]$NoClean,
    [switch]$NoPipInstall,
    [switch]$CleanInputs
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSCommandPath
Set-Location $RepoRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-InRepo {
    param([string]$Path)
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
    if (-not $resolved) {
        return $null
    }

    $fullPath = $resolved.Path
    if (-not $fullPath.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to touch path outside repository: $fullPath"
    }
    return $fullPath
}

function Remove-RepoItem {
    param([string]$Path)
    $fullPath = Assert-InRepo $Path
    if ($fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

function Test-PythonWithTk {
    param([string]$PythonPath)
    if (-not $PythonPath) {
        return $false
    }

    try {
        $version = & $PythonPath --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $false
        }

        $tkVersion = & $PythonPath -c "import tkinter; print(tkinter.TkVersion)" 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $false
        }

        Write-Host "Using Python: $PythonPath"
        Write-Host "Python version: $version"
        Write-Host "Tk version: $tkVersion"
        return $true
    }
    catch {
        return $false
    }
}

function Find-PythonWithTk {
    if ($Python) {
        if (Test-PythonWithTk $Python) {
            return $Python
        }
        throw "The Python passed via -Python does not work or has no tkinter: $Python"
    }

    $candidates = New-Object System.Collections.Generic.List[string]

    foreach ($commandName in @("python", "py")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command -and $command.Source) {
            [void]$candidates.Add($command.Source)
        }
    }

    $knownPaths = @(
        "$env:LocalAppData\Programs\Python\Python311\python.exe",
        "$env:LocalAppData\Programs\Python\Python312\python.exe",
        "$env:LocalAppData\Programs\Python\Python313\python.exe",
        "$env:LocalAppData\Programs\Python\Python310\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python313\python.exe",
        "$env:ProgramFiles\Python310\python.exe",
        "C:\Python311\python.exe",
        "C:\Python312\python.exe",
        "C:\Python313\python.exe",
        "C:\Python310\python.exe"
    )

    foreach ($path in $knownPaths) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            [void]$candidates.Add($path)
        }
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        if (-not $candidate -or $seen.ContainsKey($candidate)) {
            continue
        }
        $seen[$candidate] = $true

        if (Test-PythonWithTk $candidate) {
            return $candidate
        }
    }

    throw "Could not find a local Python with tkinter. Install Python 3.11+ from python.org, or pass -Python C:\Path\to\python.exe."
}

function Ensure-PythonDeps {
    param([string]$PythonExe)
    if ($NoPipInstall) {
        Write-Host "Skipping pip install because -NoPipInstall was passed."
        return
    }

    Write-Step "Installing Python build dependencies"
    & $PythonExe -m pip install --upgrade pip pyinstaller pillow
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed."
    }
}

function Download-File {
    param(
        [string]$Uri,
        [string]$OutFile
    )
    Write-Host "Downloading $Uri"
    Invoke-WebRequest -Uri $Uri -OutFile $OutFile
}

function Download-BuildInputs {
    Write-Step "Downloading yt-dlp, Deno and FFmpeg"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $headers = @{ Accept = "application/vnd.github+json" }

    Remove-RepoItem "yt-dlp.exe"
    Remove-RepoItem "deno"
    Remove-RepoItem "deno.zip"
    Remove-RepoItem "deno_tmp"
    Remove-RepoItem "ffmpeg"
    Remove-RepoItem "ffmpeg.zip"
    Remove-RepoItem "ffmpeg_tmp"

    $ytRel = Invoke-RestMethod -Uri "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest" -Headers $headers
    $ytAsset = $ytRel.assets | Where-Object { $_.name -like "*yt-dlp.exe" } | Select-Object -First 1
    if (-not $ytAsset) {
        throw "yt-dlp.exe release asset was not found."
    }
    Download-File $ytAsset.browser_download_url "yt-dlp.exe"

    Download-File "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" "deno.zip"
    Expand-Archive -Path "deno.zip" -DestinationPath "deno_tmp" -Force
    New-Item -ItemType Directory -Force -Path "deno" | Out-Null
    Copy-Item "deno_tmp\deno.exe" "deno\deno.exe" -Force

    $ffRel = Invoke-RestMethod -Uri "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest" -Headers $headers
    $ffAsset = $ffRel.assets |
        Where-Object { $_.name -match "win64" -and $_.name -match "shared" -and $_.name -match "\.zip$" } |
        Select-Object -First 1
    if (-not $ffAsset) {
        $ffAsset = $ffRel.assets |
            Where-Object { $_.name -match "win64" -and $_.name -match "\.zip$" } |
            Select-Object -First 1
    }
    if (-not $ffAsset) {
        throw "FFmpeg win64 zip release asset was not found."
    }

    Download-File $ffAsset.browser_download_url "ffmpeg.zip"
    Expand-Archive -Path "ffmpeg.zip" -DestinationPath "ffmpeg_tmp" -Force
    $ffmpegExe = Get-ChildItem -Path "ffmpeg_tmp" -Filter "ffmpeg.exe" -Recurse | Select-Object -First 1
    $ffprobeExe = Get-ChildItem -Path "ffmpeg_tmp" -Filter "ffprobe.exe" -Recurse | Select-Object -First 1
    if (-not $ffmpegExe -or -not $ffprobeExe) {
        throw "ffmpeg.exe or ffprobe.exe was not found in the FFmpeg archive."
    }

    New-Item -ItemType Directory -Force -Path "ffmpeg" | Out-Null
    Copy-Item $ffmpegExe.FullName "ffmpeg\ffmpeg.exe" -Force
    Copy-Item $ffprobeExe.FullName "ffmpeg\ffprobe.exe" -Force
    Get-ChildItem -Path "ffmpeg_tmp" -Filter "*.dll" -Recurse | ForEach-Object {
        Copy-Item $_.FullName "ffmpeg\" -Force
    }

    if (-not (Get-ChildItem -Path "ffmpeg" -Filter "*.dll" -ErrorAction SilentlyContinue)) {
        throw "No FFmpeg DLLs were copied. The selected FFmpeg archive is not suitable for the current PyInstaller command."
    }

    Remove-RepoItem "deno.zip"
    Remove-RepoItem "deno_tmp"
    Remove-RepoItem "ffmpeg.zip"
    Remove-RepoItem "ffmpeg_tmp"
}

function Assert-BuildInputs {
    $required = @(
        "yt-dlp.exe",
        "deno\deno.exe",
        "ffmpeg\ffmpeg.exe",
        "ffmpeg\ffprobe.exe"
    )

    foreach ($path in $required) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Required build input is missing: $path. Run without -SkipDownload to download it."
        }
    }

    if (-not (Get-ChildItem -Path "ffmpeg" -Filter "*.dll" -ErrorAction SilentlyContinue)) {
        throw "Required FFmpeg DLL files are missing. Run without -SkipDownload to download them."
    }
}

function Invoke-LocalBuild {
    param([string]$PythonExe)

    if (-not $NoClean) {
        Write-Step "Cleaning previous build output"
        Remove-RepoItem "build"
        Remove-RepoItem "dist"
        Remove-RepoItem "KirstGrab.spec"
    }

    Write-Step "Building KirstGrab.exe"
    $args = @(
        "-m", "PyInstaller",
        "-F",
        "--windowed",
        "KirstGrab.py",
        "--distpath", "dist",
        "--workpath", "build",
        "--noconfirm",
        "--icon", "icon.ico",
        "--add-data", "images/background.png;images",
        "--add-data", "fonts/m6x11plus.ttf;fonts",
        "--add-data", "icon.ico;.",
        "--add-data", "cookies.txt;.",
        "--add-binary", "yt-dlp.exe;bin",
        "--add-binary", "ffmpeg\ffmpeg.exe;bin",
        "--add-binary", "ffmpeg\ffprobe.exe;bin",
        "--add-binary", "ffmpeg\*.dll;bin",
        "--add-binary", "deno\deno.exe;bin\deno"
    )

    & $PythonExe @args
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed."
    }
}

function Test-BuildWarnings {
    $warnFile = Join-Path $RepoRoot "build\KirstGrab\warn-KirstGrab.txt"
    if (-not (Test-Path -LiteralPath $warnFile)) {
        return
    }

    $badWarnings = Select-String -Path $warnFile -Pattern "missing module named tkinter|tkinter installation is broken"
    if ($badWarnings) {
        throw "PyInstaller warning indicates tkinter was not bundled correctly. See $warnFile"
    }
}

try {
    Write-Step "Finding Python with tkinter"
    $pythonExe = Find-PythonWithTk

    Ensure-PythonDeps $pythonExe

    if (-not $SkipDownload) {
        Download-BuildInputs
    }
    else {
        Write-Step "Using existing downloaded build inputs"
    }

    Assert-BuildInputs
    Invoke-LocalBuild $pythonExe
    Test-BuildWarnings

    $exe = Get-Item -LiteralPath (Join-Path $RepoRoot "dist\KirstGrab.exe")
    $hash = Get-FileHash -LiteralPath $exe.FullName -Algorithm SHA256

    Write-Step "Build complete"
    Write-Host "EXE: $($exe.FullName)"
    Write-Host "Size: $($exe.Length) bytes"
    Write-Host "SHA256: $($hash.Hash)"

    if ($CleanInputs) {
        Write-Step "Cleaning downloaded build inputs"
        Remove-RepoItem "yt-dlp.exe"
        Remove-RepoItem "deno"
        Remove-RepoItem "ffmpeg"
    }
}
catch {
    Write-Host ""
    Write-Host "Build failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
