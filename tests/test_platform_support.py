import os
import tempfile
import unittest

from kirstgrab_platform import (
    bundled_binary_paths,
    clean_subprocess_environment,
    cookies_file_path,
    find_macos_app_bundle,
    find_macos_app_in_tree,
    normalize_architecture,
    release_platform_key,
    select_release_asset,
)


class PlatformSupportTests(unittest.TestCase):
    def test_subprocess_environment_drops_pyinstaller_process_state(self):
        original = {
            "PATH": r"C:\Windows\System32",
            "_MEIPASS2": r"C:\Temp\_MEI-old",
            "_PYI_APPLICATION_HOME_DIR": r"C:\Temp\_MEI-new",
            "_PYI_ARCHIVE_FILE": r"C:\Apps\KirstGrab.exe",
            "_PYI_PARENT_PROCESS_LEVEL": "1",
        }

        cleaned = clean_subprocess_environment(original, platform_name="win32")

        self.assertEqual(cleaned, {"PATH": r"C:\Windows\System32"})
        self.assertIn("_PYI_ARCHIVE_FILE", original)

    def test_architecture_aliases_are_normalized(self):
        self.assertEqual(normalize_architecture("AMD64"), "x86_64")
        self.assertEqual(normalize_architecture("aarch64"), "arm64")

    def test_release_platform_keys(self):
        self.assertEqual(release_platform_key("win32", "AMD64"), "windows-x86_64")
        self.assertEqual(release_platform_key("darwin", "arm64"), "macos-arm64")

    def test_macos_release_never_falls_back_to_windows_archive(self):
        assets = [
            {"name": "release-1.6.0.zip"},
            {"name": "KirstGrab-1.6.0-macos-x86_64.zip"},
            {"name": "KirstGrab-1.6.0-macos-arm64.zip"},
        ]
        selected = select_release_asset(assets, "darwin", "arm64")
        self.assertEqual(selected["name"], "KirstGrab-1.6.0-macos-arm64.zip")

    def test_windows_accepts_legacy_release_name(self):
        assets = [{"name": "release-1.6.0.zip"}]
        selected = select_release_asset(assets, "win32", "AMD64")
        self.assertEqual(selected["name"], "release-1.6.0.zip")

    def test_wrong_macos_architecture_is_rejected(self):
        assets = [{"name": "KirstGrab-1.6.0-macos-x86_64.zip"}]
        self.assertIsNone(select_release_asset(assets, "darwin", "arm64"))

    def test_universal_macos_archive_is_supported(self):
        assets = [{"name": "KirstGrab-1.6.0-macos-universal2.zip"}]
        selected = select_release_asset(assets, "darwin", "arm64")
        self.assertEqual(selected["name"], "KirstGrab-1.6.0-macos-universal2.zip")

    def test_macos_binary_names_have_no_exe_suffix(self):
        paths = bundled_binary_paths("darwin")
        self.assertEqual(paths["yt_dlp"], os.path.join("bin", "yt-dlp"))
        self.assertEqual(paths["deno"], os.path.join("bin", "deno", "deno"))

    def test_macos_cookies_live_in_application_support(self):
        path = cookies_file_path(platform_name="darwin", home="/Users/tester")
        self.assertEqual(
            path,
            "/Users/tester/Library/Application Support/KirstGrab/cookies.txt",
        )

    def test_windows_cookies_live_in_appdata(self):
        path = cookies_file_path(
            platform_name="win32",
            environ={"APPDATA": r"C:\Users\tester\AppData\Roaming"},
            home=r"C:\Users\tester",
        )
        self.assertEqual(
            path,
            r"C:\Users\tester\AppData\Roaming\KirstGrab\cookies.txt",
        )

    def test_finds_current_and_extracted_app_bundle(self):
        executable = "/Applications/KirstGrab.app/Contents/MacOS/KirstGrab"
        self.assertEqual(
            find_macos_app_bundle(executable),
            "/Applications/KirstGrab.app",
        )

        with tempfile.TemporaryDirectory() as directory:
            app_path = os.path.join(directory, "nested", "KirstGrab.app")
            os.makedirs(os.path.join(app_path, "Contents", "MacOS"))
            self.assertEqual(find_macos_app_in_tree(directory), app_path)


if __name__ == "__main__":
    unittest.main()
