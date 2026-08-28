# Third-party components

KirstGrab release bundles include separately maintained components. The CI release pins the direct build inputs; exact transitive versions and the FFmpeg configuration are recorded in the bundled `BUILD-MANIFEST.txt`.

- **yt-dlp 2026.08.19** — https://github.com/yt-dlp/yt-dlp/tree/2026.08.19. The official `yt-dlp_macos`/`yt-dlp.exe` release binary contains its generated `THIRD_PARTY_LICENSES.txt`; yt-dlp's own source is released under The Unlicense.
- **Deno 2.8.1** — https://github.com/denoland/deno/tree/v2.8.1, MIT License. Copyright the Deno authors. Permission is granted, free of charge, to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies, subject to inclusion of the copyright and permission notice. The software is provided “as is”, without warranty of any kind.
- **FFmpeg / FFprobe 9.0.1** — https://ffmpeg.org and https://github.com/Homebrew/homebrew-core/tree/master/Formula/f/ffmpeg.rb. The bundled Homebrew formula build is GPL-3.0-or-later. KirstGrab bundles the full GPLv3 text as `LICENSE`; the exact formula revision, enabled libraries, and configuration are recorded by `ffmpeg -version` in `BUILD-MANIFEST.txt`. FFmpeg source is available from https://ffmpeg.org/download.html.
- **CPython 3.13**, including Tcl/Tk — https://www.python.org/downloads/source/, PSF License Version 2 and the Tcl/Tk license.
- **Pillow 12.3.0** — https://github.com/python-pillow/Pillow/tree/12.3.0, HPND License.
- **PyInstaller 6.22.2 bootloader** — https://github.com/pyinstaller/pyinstaller/tree/v6.22.2, GPL-2.0-or-later with the project bootloader exception.

These projects are not affiliated with KirstGrab. Their names, copyrights, and licenses remain with their respective authors. The source links above correspond to the pinned direct inputs used by the release workflow.
