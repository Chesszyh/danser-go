#!/usr/bin/env python3
"""Offline synthetic staging tests; never build or modify the real checkout."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("source_packager", HERE / "package_source.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True, stderr=subprocess.DEVNULL).strip()


def repository(root):
    root.mkdir(parents=True)
    git(root, "init", "-q")
    git(root, "config", "user.name", "Source fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    write(root / "source.txt", "exact tracked source\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    return root


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = repository(self.root / "app")
        osu = repository(self.root / "upstream-osu")
        git(self.repo, "-c", "protocol.file.allow=always", "submodule", "add", str(osu), "third_party/osu")
        os.symlink("source.txt", self.repo / "safe-link")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "materialized submodule")
        write(self.repo / "untracked-private.txt", "do not include this\n")
        git(self.repo, "config", "credential.helper", "secret-fixture-never-export")
        self.deps = self.root / "deps"
        libyuv = repository(self.root / "libyuv")
        commit = git(libyuv, "rev-parse", "HEAD")
        (self.deps / "src").mkdir(parents=True)
        shutil.move(str(libyuv), str(self.deps / "src" / ("libyuv-" + commit)))
        self.sdl = self.deps / "src/SDL3-3.4.16"
        write(self.sdl / "CMakeLists.txt", "project(SDL3)\n")
        write(self.sdl / "src/main.c", "void source(void) {}\n")
        self.sdl_archive = self.deps / "archives/SDL3-3.4.16.tar.gz"
        self.sdl_archive.parent.mkdir()
        with tarfile.open(self.sdl_archive, "w:gz") as tar:
            tar.add(self.sdl, arcname=self.sdl.name)
        write(self.sdl / ".archive-sha256", p.digest(self.sdl_archive) + "\n")
        self.cache = self.root / "module-cache"
        module = self.cache / "example.org/!fork@v1.2.3"
        write(module / "go.mod", "module example.org/Fork\n")
        write(module / "native.c", "void linked_native(void) {}\n")
        self.build = self.root / "build"
        self.evidence = ("binary: go1.26.1\n\tpath\texample.org/app\n"
                         "\tdep\texample.org/Original\tv1.0.0\th1:original\n"
                         "\t=>\texample.org/Fork\tv1.2.3\th1:replacement\n")
        self.inventory = {"packages": [{"ecosystem": "Go", "key": "example.org/Fork@v1.2.3",
                                       "sourceDirectory": str(module)}], "fatalErrors": [], "binaries": []}
        write(self.build / "collected-notices/Evidence/go-build-info.txt", self.evidence)
        self.save_inventory()
        write(self.build / "build-info.json", json.dumps({"sourceRevision": git(self.repo, "rev-parse", "HEAD"),
              "osuSourceRevision": git(self.repo / "third_party/osu", "rev-parse", "HEAD")}))
        write(self.build / "danser.app/Contents/MacOS/danser", "fixture only")
        self.tooling = self.root / "tooling"
        self.tooling.mkdir()
        for name in ("package_source.py", "README-source.md", "build-ffmpeg-from-bundled-source.sh"):
            shutil.copyfile(HERE / name, self.tooling / name)
        self.pins = {"native": {"libyuv": {"commit": commit},
                               "SDL3": {"version": "3.4.16", "sha256": p.digest(self.sdl_archive)}},
                     "archives": [], "materials": []}
        self.archive_cache = self.root / "source-archives"
        self.args = argparse.Namespace(repo=self.repo, build_dir=self.build, deps=self.deps,
                                       go_mod_cache=self.cache, archives_cache=self.archive_cache,
                                       out=None, fetch=False)
        self.real_run = p.run

    def tearDown(self):
        self.temp.cleanup()

    def save_inventory(self):
        write(self.build / "collected-notices/inventory.json", json.dumps(self.inventory))

    def fake_run(self, *args, **kwargs):
        if args[0] == "go":
            self.assertEqual(args[1:3], ("version", "-m"))
            return self.evidence.strip()
        return self.real_run(*args, **kwargs)

    def package(self):
        write(self.tooling / "sources.json", json.dumps(self.pins))
        with patch.object(p, "__file__", str(self.tooling / "package_source.py")), patch.object(p, "run", self.fake_run):
            p.package(self.args)
        return self.build / "danser-macos-source.tar.gz"

    def test_core_staging(self):
        archive = self.package()
        with tarfile.open(archive) as tar:
            names = tar.getnames()
            prefix = "danser-macos-source/"
            self.assertIn(prefix + "application/third_party/osu/source.txt", names)
            self.assertIn(prefix + "go-modules/example.org/!fork@v1.2.3/native.c", names)
            self.assertIn(prefix + "native/libyuv/source.txt", names)
            self.assertIn(prefix + "native/SDL3-3.4.16/src/main.c", names)
            self.assertFalse(any(".git/" in x or x.endswith("/.git") or "private" in x for x in names))
            self.assertTrue(tar.getmember(prefix + "application/safe-link").issym())
            manifest = json.load(tar.extractfile(prefix + "source-manifest.json"))
            self.assertFalse(manifest["optionalRulesHostIncluded"])
            self.assertEqual(manifest["goModules"][0]["original"]["replacement"]["path"], "example.org/Fork")
        self.assertTrue(archive.with_name(archive.name + ".sha256").is_file())

    def test_host_staging(self):
        (self.build / "danser.app/Contents/MacOS/lazer-rules-host").mkdir()
        self.inventory["packages"].append({"ecosystem": "NuGet", "key": "Native/1.0", "packageSha256": "aa"})
        ff = {"nugetPackage": "Native/1.0", "nugetPackageSha256": "aa", "binaries": []}
        write(self.tooling / "materials/ffmpeg-notices/SOURCES.json", json.dumps(ff))
        write(self.tooling / "materials/lgpl-sources/SOURCES.json", '{"packages": []}')
        for file in (self.tooling / "materials").rglob("*.json"):
            self.pins["materials"].append({"file": str(file.relative_to(self.tooling / "materials")),
                                            "sha256": p.digest(file), "when": "host"})
        write(self.archive_cache / "lgpl-sources/pinned.tar.gz", "synthetic archive bytes")
        self.pins["archives"].append({"file": "lgpl-sources/pinned.tar.gz", "when": "host",
                                      "sha256": p.digest(self.archive_cache / "lgpl-sources/pinned.tar.gz")})
        self.save_inventory()
        with tarfile.open(self.package()) as tar:
            self.assertIn("danser-macos-source/upstream/lgpl-sources/pinned.tar.gz", tar.getnames())

    def test_dirty_source_rejected(self):
        write(self.repo / "source.txt", "modified after build")
        with self.assertRaisesRegex(ValueError, "dirty"):
            self.package()
        self.assertFalse((self.build / "danser-macos-source.tar.gz").exists())

    def test_revision_mismatch_rejected(self):
        write(self.build / "build-info.json", '{"sourceRevision": "different"}')
        with self.assertRaisesRegex(ValueError, "revision mismatch"):
            self.package()

    def test_whole_home_copy_rejected(self):
        self.inventory["packages"][0]["sourceDirectory"] = str(self.root)
        self.save_inventory()
        with self.assertRaisesRegex(ValueError, "exact module-cache"):
            self.package()

    def test_changed_sdl_rejected(self):
        write(self.sdl / "src/main.c", "modified")
        with self.assertRaisesRegex(ValueError, "differs from pinned archive"):
            self.package()

    def test_pre_module_source(self):
        (self.cache / "example.org/!fork@v1.2.3/go.mod").unlink()
        write(self.cache / "cache/download/example.org/!fork/@v/v1.2.3.mod", "module example.org/Fork\n")
        write(self.cache / "cache/download/example.org/!fork/@v/v1.2.3.ziphash", "h1:replacement\n")
        with tarfile.open(self.package()) as tar:
            self.assertIn("danser-macos-source/go-module-metadata/example.org/!fork@v1.2.3/v1.2.3.mod", tar.getnames())
            self.assertNotIn("danser-macos-source/go-modules/example.org/!fork@v1.2.3/go.mod", tar.getnames())

    def test_escaping_symlink_rejected(self):
        repo = repository(self.root / "escaping-repo")
        os.symlink("../outside", repo / "bad")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "link")
        with self.assertRaisesRegex(ValueError, "escapes"):
            p.export_git(repo, self.root / "export")

    def test_archive_mismatch_rejected(self):
        write(self.archive_cache / "bad.tar.gz", "different")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            p.source_archive({"file": "bad.tar.gz", "sha256": "0" * 64}, self.archive_cache,
                             self.root / "bad-output.tar.gz", False)

    def test_incomplete_notices_rejected(self):
        self.inventory["fatalErrors"] = ["missing component"]
        self.save_inventory()
        with self.assertRaisesRegex(ValueError, "fatal errors"):
            self.package()

    def test_resource_staging_is_confined_and_audited(self):
        source, kit = self.root / "resource-source", self.root / "resource-kit"
        lock = {"files": {}}
        for name in ("LICENCE.md", "README.md"):
            data = (name + " verified source\n").encode()
            write(source / name, data.decode())
            lock["files"][name] = {"size": len(data), "git_blob_sha1":
                p.hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}
        write(source / "osu.Game.Resources/Fonts/OPEN_FONT_PROVENANCE.json", '{"fixture": true}')
        write(source / "osu.Game.Resources/Fonts/open.png", "open font payload")
        write(source / "osu.Game.Resources/bin/private.dll", "excluded build")
        write(source / "osu.Game.Resources/obj/private.nupkg", "excluded build")
        write(source / ".git/config", "excluded credentials")
        write(source / "old.nupkg", "excluded upstream package")
        write(kit / "pinned-resource-lock.json", json.dumps(lock))
        write(kit / "replace_restricted_fonts.py", "import json\nprint(json.dumps({'status':'passed','restricted_original_payloads':0}))\n")
        destination = self.root / "staged-resources"
        record = p.package_resources(source, kit, destination)
        self.assertEqual(record["sourceAudit"]["status"], "passed")
        files = [r["path"] for r in p.file_manifest(destination)]
        self.assertIn("replacement-tools/replace_restricted_fonts.py", files)
        self.assertIn("osu.Game.Resources/Fonts/open.png", files)
        self.assertFalse(any("bin/" in x or "obj/" in x or ".git/" in x or "nupkg" in x for x in files))

    def test_open_font_release_requires_source(self):
        (self.build / "danser.app/Contents/MacOS/lazer-rules-host").mkdir()
        self.args.require_open_font_sources = True
        with self.assertRaisesRegex(ValueError, "requires audited modified resource source"):
            self.package()


if __name__ == "__main__":
    unittest.main()
