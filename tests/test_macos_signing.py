import unittest
from pathlib import Path

from scripts.sign_macos_bundle import codesign_command


class MacOSSigningTests(unittest.TestCase):
    def test_developer_id_signing_uses_runtime_timestamp_and_entitlements(self):
        command = codesign_command(
            "Developer ID Application: Example (TEAMID)",
            Path("KirstGrab.app"),
            Path("helper-entitlements.plist"),
        )
        self.assertIn("runtime", command)
        self.assertIn("--timestamp", command)
        self.assertEqual(command[-2:], ["helper-entitlements.plist", "KirstGrab.app"])

    def test_adhoc_signing_has_no_timestamp_and_deep_is_explicit(self):
        command = codesign_command(
            "-",
            Path("KirstGrab.app"),
            Path("app-entitlements.plist"),
            deep=True,
        )
        self.assertIn("--deep", command)
        self.assertNotIn("--timestamp", command)


if __name__ == "__main__":
    unittest.main()
