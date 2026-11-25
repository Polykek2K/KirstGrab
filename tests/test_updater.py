import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from kirstgrab_updater import (
    download_release_archive,
    extract_release_archive,
    find_update_payload,
    launch_update_helper,
    release_sha256,
)


class DownloadTests(unittest.TestCase):
    def test_release_digest_must_be_a_complete_sha256(self):
        valid_hash = "Ab" * 32
        self.assertEqual(release_sha256({"digest": f"SHA256:{valid_hash}"}), valid_hash.lower())
        for digest in (None, "sha256:12", "sha1:" + valid_hash):
            with self.subTest(digest=digest):
                self.assertIsNone(release_sha256({"digest": digest}))

    def test_download_is_verified_before_the_archive_can_be_used(self):
        contents = b"KirstGrab release"
        digest = hashlib.sha256(contents).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "release.zip"
            for expected in (digest, "0" * 64):
                with self.subTest(expected=expected), io.BytesIO(contents) as response:
                    response.headers = {"Content-Length": str(len(contents))}
                    progress = []
                    with patch("kirstgrab_updater.urllib.request.urlopen", return_value=response):
                        arguments = ("https://example.test/update.zip", destination, expected, progress.append)
                        if expected == digest:
                            download_release_archive(*arguments)
                            self.assertEqual(destination.read_bytes(), contents)
                            self.assertEqual(progress[-1], 100)
                        else:
                            with self.assertRaisesRegex(ValueError, "SHA-256 verification"):
                                download_release_archive(*arguments)

    def test_windows_release_uses_the_packaged_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "release.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("KirstGrab Helper.exe", b"helper")
                archive.writestr("release/KirstGrab.exe", b"application")
            extracted = root / "extracted"
            with patch("kirstgrab_updater.sys.platform", "win32"):
                extract_release_archive(archive_path, extracted)
                source = find_update_payload(extracted, root / "installed.exe", "1.6.7")
            self.assertEqual(source, extracted / "release" / "KirstGrab.exe")


class HelperHandoffTests(unittest.TestCase):
    def test_helper_failure_leaves_the_update_unconfirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            process = Mock()
            process.poll.return_value = 1
            with patch("kirstgrab_updater.sys.platform", "darwin"), patch(
                "kirstgrab_updater.subprocess.Popen", return_value=process
            ):
                with self.assertRaisesRegex(OSError, "did not get ready"):
                    launch_update_helper(work, work / "source.app", work / "KirstGrab.app")
            self.assertFalse((work / "handoff").exists())
