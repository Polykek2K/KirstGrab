import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.verify_sha256 import expected_digest, verify_file


class VerifySha256Tests(unittest.TestCase):
    def test_selects_named_gnu_checksum(self):
        digest = "a" * 64
        checksums = f"{'b' * 64}  other.zip\n{digest} *tool.exe\n"
        self.assertEqual(expected_digest(checksums, "tool.exe"), digest)

    def test_accepts_single_unnamed_checksum(self):
        digest = "c" * 64
        self.assertEqual(expected_digest(f"{digest}\n", "archive.zip"), digest)

    def test_accepts_windows_powershell_checksum(self):
        digest = "c1" * 32
        checksums = "\n".join(
            (
                "Algorithm : SHA256",
                f"Hash      : {digest.upper()}",
                r"Path      : D:\a\deno\deno-x86_64-pc-windows-msvc.zip",
            )
        )
        self.assertEqual(
            expected_digest(checksums, "deno-x86_64-pc-windows-msvc.zip"), digest
        )

    def test_rejects_missing_entry(self):
        with self.assertRaises(ValueError):
            expected_digest(f"{'d' * 64}  other.zip\n", "archive.zip")

    def test_does_not_fall_back_to_unnamed_checksum_in_named_list(self):
        checksums = f"{'e' * 64}\n{'f' * 64}  other.zip\n"
        with self.assertRaises(ValueError):
            expected_digest(checksums, "archive.zip")

    def test_verifies_file_and_rejects_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloaded = root / "archive.zip"
            checksums = root / "checksums.txt"
            downloaded.write_bytes(b"KirstGrab")
            digest = hashlib.sha256(b"KirstGrab").hexdigest()
            checksums.write_text(f"{digest}  archive.zip\n", encoding="utf-8")

            self.assertEqual(verify_file(downloaded, checksums, "archive.zip"), digest)

            downloaded.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                verify_file(downloaded, checksums, "archive.zip")


if __name__ == "__main__":
    unittest.main()
