#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR"

PYTHON_BIN=${PYTHON_BIN:-python3}
PYINSTALLER_VERSION=6.22.2
PYINSTALLER_HOOKS_VERSION=2026.7
PILLOW_VERSION=12.3.0
ALTGRAPH_VERSION=0.17.4
MACHOLIB_VERSION=1.16.3
PACKAGING_VERSION=26.3
SETUPTOOLS_VERSION=80.9.0
YT_DLP_VERSION=2026.08.19
DENO_VERSION=2.8.1
FFMPEG_VERSION=9.0.1
VERSION=""
SKIP_DOWNLOAD=0
NO_CLEAN=0
NO_PIP_INSTALL=0
CLEAN_INPUTS=0

usage() {
    echo "Usage: ./build-local-macos.sh [--version X.Y.Z] [--skip-download] [--no-clean] [--no-pip-install] [--clean-inputs]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --version)
            VERSION=${2:?"--version requires a value"}
            shift 2
            ;;
        --skip-download)
            SKIP_DOWNLOAD=1
            shift
            ;;
        --no-clean)
            NO_CLEAN=1
            shift
            ;;
        --no-pip-install)
            NO_PIP_INSTALL=1
            shift
            ;;
        --clean-inputs)
            CLEAN_INPUTS=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ "$(uname -s)" != "Darwin" ]; then
    echo "This build script must run on macOS." >&2
    exit 1
fi

ARCH=$(uname -m)
case "$ARCH" in
    arm64)
        DENO_ARCH=aarch64
        ;;
    x86_64)
        DENO_ARCH=x86_64
        ;;
    *)
        echo "Unsupported macOS architecture: $ARCH" >&2
        exit 1
        ;;
esac

SOURCE_VERSION=$(
    "$PYTHON_BIN" -c 'import re; print(re.search(r"^CURRENT_VERSION = \"([^\"]+)\"", open("KirstGrab.py", encoding="utf-8").read(), re.M).group(1))'
)
if [ -z "$VERSION" ]; then
    VERSION=$SOURCE_VERSION
fi
if [ "$VERSION" != "$SOURCE_VERSION" ]; then
    echo "Requested version $VERSION does not match CURRENT_VERSION $SOURCE_VERSION." >&2
    exit 1
fi
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Version must be a numeric X.Y.Z value suitable for CFBundleVersion." >&2
    exit 1
fi

INPUT_DIR="$SCRIPT_DIR/macos-inputs/$ARCH"
YT_DLP_PATH="$INPUT_DIR/yt-dlp"
DENO_PATH="$INPUT_DIR/deno"
DENO_ZIP="$INPUT_DIR/deno.zip"
APP_PATH="$SCRIPT_DIR/dist/KirstGrab.app"
ARCHIVE_PATH="$SCRIPT_DIR/KirstGrab-$VERSION-macos-$ARCH.zip"
BUILD_PATH="$SCRIPT_DIR/build/macos-$ARCH"

echo "==> Building KirstGrab $VERSION for macOS $ARCH"
PYTHON_SERIES=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$PYTHON_SERIES" != "3.13" ]; then
    echo "Python 3.13 is required; found $PYTHON_SERIES." >&2
    exit 1
fi
"$PYTHON_BIN" -c 'import tkinter; print(f"Python tkinter {tkinter.TkVersion}")'

if [ "$NO_PIP_INSTALL" -eq 0 ]; then
    "$PYTHON_BIN" -m pip install --disable-pip-version-check \
        --only-binary=:all: \
        "pyinstaller==$PYINSTALLER_VERSION" \
        "pyinstaller-hooks-contrib==$PYINSTALLER_HOOKS_VERSION" \
        "pillow==$PILLOW_VERSION" \
        "altgraph==$ALTGRAPH_VERSION" \
        "macholib==$MACHOLIB_VERSION" \
        "packaging==$PACKAGING_VERSION" \
        "setuptools==$SETUPTOOLS_VERSION"
fi

mkdir -p "$INPUT_DIR"
if [ "$SKIP_DOWNLOAD" -eq 0 ]; then
    echo "==> Downloading yt-dlp and Deno"
    curl --fail --location --retry 3 \
        "https://github.com/yt-dlp/yt-dlp/releases/download/$YT_DLP_VERSION/yt-dlp_macos" \
        --output "$YT_DLP_PATH"

    YT_EXPECTED=$(curl --fail --location --retry 3 \
        "https://github.com/yt-dlp/yt-dlp/releases/download/$YT_DLP_VERSION/SHA2-256SUMS" |
        awk '$2 == "yt-dlp_macos" { print $1; exit }')
    YT_ACTUAL=$(shasum -a 256 "$YT_DLP_PATH" | awk '{ print $1 }')
    if [ -z "$YT_EXPECTED" ] || [ "$YT_EXPECTED" != "$YT_ACTUAL" ]; then
        echo "yt-dlp SHA-256 verification failed." >&2
        exit 1
    fi

    DENO_ASSET="deno-$DENO_ARCH-apple-darwin.zip"
    DENO_URL="https://github.com/denoland/deno/releases/download/v$DENO_VERSION/$DENO_ASSET"
    curl --fail --location --retry 3 "$DENO_URL" --output "$DENO_ZIP"
    curl --fail --location --retry 3 "$DENO_URL.sha256sum" --output "$DENO_ZIP.sha256sum"
    DENO_EXPECTED=$(awk '{ print $1; exit }' "$DENO_ZIP.sha256sum")
    DENO_ACTUAL=$(shasum -a 256 "$DENO_ZIP" | awk '{ print $1 }')
    if [ -z "$DENO_EXPECTED" ] || [ "$DENO_EXPECTED" != "$DENO_ACTUAL" ]; then
        echo "Deno SHA-256 verification failed." >&2
        exit 1
    fi
    rm -rf "$INPUT_DIR/deno-extract"
    ditto -x -k "$DENO_ZIP" "$INPUT_DIR/deno-extract"
    mv "$INPUT_DIR/deno-extract/deno" "$DENO_PATH"
    rm -rf "$INPUT_DIR/deno-extract"
    rm -f "$DENO_ZIP" "$DENO_ZIP.sha256sum"
fi

if [ ! -f "$YT_DLP_PATH" ] || [ ! -f "$DENO_PATH" ]; then
    echo "Missing macOS build inputs. Run without --skip-download." >&2
    exit 1
fi
chmod 755 "$YT_DLP_PATH" "$DENO_PATH"
"$YT_DLP_PATH" --version
"$DENO_PATH" --version

if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is required to provide FFmpeg for the macOS bundle." >&2
    exit 1
fi

if ! brew list --versions ffmpeg >/dev/null 2>&1; then
    echo "==> Installing FFmpeg with Homebrew"
    brew install ffmpeg
fi

INSTALLED_FFMPEG_VERSION=$(brew list --versions ffmpeg | awk '{ print $2; exit }')
INSTALLED_FFMPEG_UPSTREAM_VERSION=${INSTALLED_FFMPEG_VERSION%%_*}
if [ "$INSTALLED_FFMPEG_UPSTREAM_VERSION" != "$FFMPEG_VERSION" ] && \
        [ "${KIRSTGRAB_REFRESH_HOMEBREW:-0}" = "1" ]; then
    echo "==> Updating Homebrew FFmpeg $INSTALLED_FFMPEG_VERSION to $FFMPEG_VERSION"
    brew update
    brew upgrade ffmpeg
    INSTALLED_FFMPEG_VERSION=$(brew list --versions ffmpeg | awk '{ print $2; exit }')
    INSTALLED_FFMPEG_UPSTREAM_VERSION=${INSTALLED_FFMPEG_VERSION%%_*}
fi

export HOMEBREW_NO_AUTO_UPDATE=1
if [ "$INSTALLED_FFMPEG_UPSTREAM_VERSION" != "$FFMPEG_VERSION" ]; then
    echo "Expected Homebrew FFmpeg $FFMPEG_VERSION, found $INSTALLED_FFMPEG_VERSION." >&2
    echo "Run brew update && brew upgrade ffmpeg, or update the pinned version and notices as one reviewed change." >&2
    exit 1
fi

FFMPEG_PREFIX=$(brew --prefix ffmpeg)
FFMPEG_PATH="$FFMPEG_PREFIX/bin/ffmpeg"
FFPROBE_PATH="$FFMPEG_PREFIX/bin/ffprobe"
if [ ! -x "$FFMPEG_PATH" ] || [ ! -x "$FFPROBE_PATH" ]; then
    echo "Homebrew FFmpeg installation is incomplete." >&2
    exit 1
fi

if [ "$NO_CLEAN" -eq 0 ]; then
    echo "==> Cleaning previous macOS build output"
    rm -rf "$BUILD_PATH" "$APP_PATH"
fi
mkdir -p "$BUILD_PATH" "$SCRIPT_DIR/dist"

PYINSTALLER_ACTUAL=$("$PYTHON_BIN" -c 'import PyInstaller; print(PyInstaller.__version__)')
PILLOW_ACTUAL=$("$PYTHON_BIN" -c 'import PIL; print(PIL.__version__)')
if [ "$PYINSTALLER_ACTUAL" != "$PYINSTALLER_VERSION" ] || [ "$PILLOW_ACTUAL" != "$PILLOW_VERSION" ]; then
    echo "Pinned Python build dependencies are not installed." >&2
    exit 1
fi

BUILD_MANIFEST="$BUILD_PATH/BUILD-MANIFEST.txt"
{
    echo "KirstGrab=$VERSION"
    echo "target=macOS-$ARCH"
    echo "deployment_target=${MACOSX_DEPLOYMENT_TARGET:-15.0}"
    echo "python=$("$PYTHON_BIN" -c 'import platform; print(platform.python_version())')"
    echo "pyinstaller=$PYINSTALLER_ACTUAL"
    echo "pillow=$PILLOW_ACTUAL"
    echo "yt-dlp=$YT_DLP_VERSION"
    echo "deno=$DENO_VERSION"
    echo "ffmpeg-homebrew=$INSTALLED_FFMPEG_VERSION"
    echo
    echo "[Python packages]"
    "$PYTHON_BIN" -m pip freeze
    echo
    echo "[FFmpeg build]"
    "$FFMPEG_PATH" -version
    echo
    echo "[Homebrew FFmpeg dependency tree]"
    brew deps --installed --tree ffmpeg
} > "$BUILD_MANIFEST"

echo "==> Building KirstGrab.app"
export MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET:-15.0}
PYINSTALLER_ARGS=(
    --onedir
    --windowed
    --name KirstGrab
    --distpath "$SCRIPT_DIR/dist"
    --workpath "$BUILD_PATH/work"
    --specpath "$BUILD_PATH"
    --noconfirm
    --clean
    --target-arch "$ARCH"
    --osx-bundle-identifier com.polykek2k.kirstgrab
    --osx-entitlements-file "$SCRIPT_DIR/macos-entitlements.plist"
    --icon "$SCRIPT_DIR/icon.ico"
    --add-data "$SCRIPT_DIR/images/background.png:images"
    --add-data "$SCRIPT_DIR/fonts/m6x11plus.ttf:fonts"
    --add-data "$SCRIPT_DIR/LICENSE:."
    --add-data "$SCRIPT_DIR/THIRD_PARTY_NOTICES.md:."
    --add-data "$BUILD_MANIFEST:."
    --add-binary "$YT_DLP_PATH:bin"
    --add-binary "$FFMPEG_PATH:bin"
    --add-binary "$FFPROBE_PATH:bin"
    --add-binary "$DENO_PATH:bin/deno"
)

if [ -n "${KIRSTGRAB_CODESIGN_IDENTITY:-}" ]; then
    PYINSTALLER_ARGS+=(--codesign-identity "$KIRSTGRAB_CODESIGN_IDENTITY")
fi

"$PYTHON_BIN" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$SCRIPT_DIR/KirstGrab.py"

PLIST="$APP_PATH/Contents/Info.plist"
set_plist_value() {
    local key=$1
    local type=$2
    local value=$3
    /usr/libexec/PlistBuddy -c "Set :$key $value" "$PLIST" 2>/dev/null || \
        /usr/libexec/PlistBuddy -c "Add :$key $type $value" "$PLIST"
}

set_plist_value CFBundleShortVersionString string "$VERSION"
set_plist_value CFBundleVersion string "$VERSION"
set_plist_value LSMinimumSystemVersion string "$MACOSX_DEPLOYMENT_TARGET"
set_plist_value NSHighResolutionCapable bool true

if [ -n "${KIRSTGRAB_CODESIGN_IDENTITY:-}" ]; then
    codesign --force --sign "$KIRSTGRAB_CODESIGN_IDENTITY" --options runtime --timestamp \
        --entitlements "$SCRIPT_DIR/macos-entitlements.plist" "$APP_PATH"
else
    codesign --force --sign - --options runtime \
        --entitlements "$SCRIPT_DIR/macos-entitlements.plist" "$APP_PATH"
fi

"$PYTHON_BIN" "$SCRIPT_DIR/scripts/verify_macos_bundle.py" \
    "$APP_PATH" --architecture "$ARCH" --version "$VERSION"

echo "==> Creating release archive"
rm -f "$ARCHIVE_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ARCHIVE_PATH"
shasum -a 256 "$ARCHIVE_PATH"

if [ "$CLEAN_INPUTS" -eq 1 ]; then
    rm -rf "$INPUT_DIR"
fi

echo "APP: $APP_PATH"
echo "ZIP: $ARCHIVE_PATH"
