# Third-party components

KirstGrab release bundles include separately maintained components. The build resolves the latest available releases instead of pinning exact dependency versions; the exact selected versions, Python packages, and FFmpeg configuration are recorded in the bundled `BUILD-MANIFEST.txt`.

- **yt-dlp** — https://github.com/yt-dlp/yt-dlp/releases/latest. The official `yt-dlp_macos`/`yt-dlp.exe` release binary contains its generated `THIRD_PARTY_LICENSES.txt`; yt-dlp's own source is released under The Unlicense.
- **Deno** — https://github.com/denoland/deno/releases/latest, MIT License. Copyright the Deno authors. Permission is granted, free of charge, to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies, subject to inclusion of the copyright and permission notice. The software is provided “as is”, without warranty of any kind.
- **FFmpeg / FFprobe** — https://ffmpeg.org, https://github.com/BtbN/FFmpeg-Builds/releases/latest, and https://github.com/Homebrew/homebrew-core/blob/master/Formula/f/ffmpeg.rb. Bundled builds are GPL-3.0-or-later. KirstGrab bundles the full GPLv3 text as `LICENSE`; the exact build, enabled libraries, and configuration are recorded by `ffmpeg -version` in `BUILD-MANIFEST.txt`. FFmpeg source is available from https://ffmpeg.org/download.html.
- **CPython 3.13**, including Tcl/Tk — https://www.python.org/downloads/source/, PSF License Version 2 and the Tcl/Tk license.
- **Pillow** — https://github.com/python-pillow/Pillow/releases/latest, HPND License.
- **PyInstaller bootloader** — https://github.com/pyinstaller/pyinstaller/releases/latest, GPL-2.0-or-later with the project bootloader exception.

These projects are not affiliated with KirstGrab. Their names, copyrights, and licenses remain with their respective authors. Use `BUILD-MANIFEST.txt` from a release artifact to identify the exact source revisions selected by that build.
