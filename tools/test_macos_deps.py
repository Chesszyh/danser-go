#!/usr/bin/env python3
"""Platform-independent cache/transfer tests; does not compile macOS code."""

import hashlib
import io
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import unittest
import zipfile


class DependencyCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="danser deps test ")
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        source = Path(__file__).with_name("macos-deps.sh").read_text()
        helpers = source.split("valid_archive() {", 1)[1].split('\ndownload "https:', 1)[0]
        self.helpers = self.root / "helpers.sh"
        self.helpers.write_text("set -eu\nvalid_archive() {" + helpers)
        curl = self.bin / "curl"
        curl.write_text("""#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$MOCK_LOG"
while [ "$#" -gt 0 ]; do
    if [ "$1" = -o ]; then output=$2; break; fi
    shift
done
if [ "${MOCK_FAIL:-0}" = 1 ]; then
    printf partial > "$output"
    exit 56
fi
cp "$MOCK_SOURCE" "$output"
""")
        curl.chmod(0o755)
        self.archive = self.root / "official.zip"
        with zipfile.ZipFile(self.archive, "w") as out:
            out.writestr("library", "known content")
        self.destination = self.root / "cached.zip"
        self.log = self.root / "curl.log"
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        MOCK_SOURCE=str(self.archive), MOCK_LOG=str(self.log))

    def tearDown(self):
        self.temp.cleanup()

    def run_shell(self, command, succeeds=True, **env):
        result = subprocess.run(["sh", "-c", '. "$1"; ' + command, "test", str(self.helpers)],
                                env=dict(self.env, **env), capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, succeeds, result.stdout + result.stderr)
        return result

    def download(self, checksum="", **kwargs):
        return self.run_shell("download https://example.invalid/dependency.zip " +
                              shlex.quote(str(self.destination)) + " " + shlex.quote(checksum), **kwargs)

    def test_valid_cache_avoids_network(self):
        self.destination.write_bytes(self.archive.read_bytes())
        self.download()
        self.assertFalse(self.log.exists())

    def test_corrupt_cache_is_replaced_atomically(self):
        self.destination.write_bytes(b"partial")
        self.download()
        self.assertEqual(self.destination.read_bytes(), self.archive.read_bytes())
        self.assertIn("--retry-all-errors", self.log.read_text())
        self.assertEqual(list(self.root.glob("*.partial.*")), [])

    def test_failed_transfer_never_promotes_partial(self):
        self.download(succeeds=False, MOCK_FAIL="1")
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob("*.partial.*")), [])

    def test_invalid_download_is_rejected(self):
        self.archive.write_bytes(b"HTTP error document")
        self.download(succeeds=False)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob("*.partial.*")), [])

    def test_checksum_mismatch_is_rejected(self):
        self.download("0" * 64, succeeds=False)
        self.assertFalse(self.destination.exists())

    def test_checksum_mismatch_cache_can_recover(self):
        with zipfile.ZipFile(self.destination, "w") as out:
            out.writestr("library", "old content")
        self.download(hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertEqual(self.destination.read_bytes(), self.archive.read_bytes())

    def test_source_tree_is_bound_to_archive_digest(self):
        archive = self.root / "source.tar.gz"
        destination = self.root / "source"
        destination.mkdir()
        (destination / "CMakeLists.txt").write_text("wrong version")
        with tarfile.open(archive, "w:gz") as out:
            entry = tarfile.TarInfo("source/CMakeLists.txt")
            content = b"correct version"
            entry.size = len(content)
            out.addfile(entry, io.BytesIO(content))
        command = "extract_archive " + shlex.quote(str(archive)) + " " + shlex.quote(str(destination)) + " 1"
        self.run_shell(command)
        self.assertEqual((destination / "CMakeLists.txt").read_text(), "correct version")
        self.assertEqual((destination / ".archive-sha256").read_text().strip(),
                         hashlib.sha256(archive.read_bytes()).hexdigest())
        self.run_shell(command)
        self.assertEqual(list(self.root.glob("*.partial.*")), [])

    def test_invalid_source_does_not_replace_existing_tree(self):
        archive = self.root / "empty.tar.gz"
        with tarfile.open(archive, "w:gz"):
            pass
        destination = self.root / "source"
        destination.mkdir()
        (destination / "CMakeLists.txt").write_text("keep existing")
        self.run_shell("extract_archive " + shlex.quote(str(archive)) + " " +
                       shlex.quote(str(destination)) + " 0", succeeds=False)
        self.assertEqual((destination / "CMakeLists.txt").read_text(), "keep existing")
        self.assertEqual(list(self.root.glob("*.partial.*")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
