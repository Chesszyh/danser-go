import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("collector", ROOT / "collect_notices.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Tests(unittest.TestCase):
    def _supplement_zip(self, root, packages, files, warnings=None):
        archive = root / "supplement.zip"
        manifest = {"packages": packages, "unresolvedByCollection": warnings or {}}
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest))
            for name, data in files.items():
                bundle.writestr(name, data)
        return archive

    def _notice_record(self, name, data):
        return {"file": name, "sha256": m.sha(data),
                "sourceUrl": "https://example.test/pinned/LICENSE"}

    def _minimal_host_command(self, root):
        host = root / "host"; host.mkdir()
        (host / "host.deps.json").write_text(json.dumps({"libraries": {}}))
        native = root / "native"; native.mkdir()
        for name in m.REQUIRED_NATIVE:
            (native / name).write_text("Test-only native licence")
        goroot = root / "goroot"; goroot.mkdir()
        (goroot / "LICENSE").write_text("Test-only Go licence")
        build = root / "go.txt"; build.write_text("")
        modules = root / "modules.json"; modules.write_text("")
        cmd = [sys.executable, str(ROOT / "collect_notices.py"),
               "--host", str(host), "--native-notices", str(native),
               "--go-build-info", str(build), "--go-module-list", str(modules),
               "--go-root", str(goroot),
               "--supplemental-notices", str(root / "no-supplement.zip")]
        return host, cmd

    def test_supplement_matches_exact_key_and_preserves_scope_warnings(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            c = m.Collector(root / "out")
            missing = "No readable notice body in Demo/1.0.0; resolve exact source/standard licence plus copyright"
            unrelated = "Demo/1.0.0: native payload needs separate scope review"
            c.records = [{"ecosystem": "NuGet", "key": "Demo/1.0.0", "notices": []}]
            c.gaps = [missing, unrelated]
            data = b"Test-only complete licence and copyright\n"
            warnings = {"fixture": [{"package": "Demo/1.0.0", "kind": "source-provenance"}]}
            archive = self._supplement_zip(root, {
                "Demo/1.0.0": {"notices": [self._notice_record("notices/LICENSE", data)]},
                # An absent package/version must not even read its missing file.
                "Demo/2.0.0": {"notices": [self._notice_record("unused/LICENSE", data)]}},
                {"notices/LICENSE": data}, warnings)
            c.supplement(archive)
            self.assertFalse(c.errors)
            self.assertNotIn(missing, c.gaps)
            self.assertIn(unrelated, c.gaps)
            self.assertEqual(len(c.records[0]["notices"]), 1)
            notice = c.records[0]["notices"][0]
            self.assertEqual(notice["sha256"], m.sha(data))
            self.assertEqual((c.out / notice["file"]).read_bytes(), data)
            self.assertEqual(json.loads((c.out / "Supplemental/UPSTREAM-SCOPE-NOTES.json").read_text()), warnings)

    def test_supplement_does_not_match_another_version(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            c = m.Collector(root / "out")
            c.records = [{"ecosystem": "NuGet", "key": "Demo/2.0.0", "notices": []}]
            c.gaps = ["Unresolved Demo/2.0.0"]
            data = b"Test-only licence"
            archive = self._supplement_zip(root, {
                "Demo/1.0.0": {"notices": [self._notice_record("LICENSE", data)]}},
                {"LICENSE": data})
            c.supplement(archive)
            self.assertEqual(c.gaps, ["Unresolved Demo/2.0.0"])
            self.assertFalse(c.records[0]["notices"])
            self.assertFalse((c.out / "Supplemental").exists())

    def test_supplement_hash_mismatch_fails_closed_and_keeps_gap(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            c = m.Collector(root / "out")
            missing = "No readable notice body in Demo/1.0.0; resolve exact source/standard licence plus copyright"
            c.records = [{"ecosystem": "NuGet", "key": "Demo/1.0.0", "notices": []}]
            c.gaps = [missing]
            archive = self._supplement_zip(root, {
                "Demo/1.0.0": {"notices": [self._notice_record("LICENSE", b"Expected licence")]}},
                {"LICENSE": b"Tampered licence"})
            c.supplement(archive)
            c.finish()
            self.assertEqual(c.errors, ["Supplemental notice hash mismatch: LICENSE"])
            self.assertIn(missing, c.gaps)
            self.assertFalse(c.records[0]["notices"])
            self.assertFalse((c.out / "Supplemental/LICENSE").exists())
            saved = json.loads((c.out / "inventory.json").read_text())
            self.assertEqual(saved["fatalErrors"], c.errors)

    def test_supplement_hash_mismatch_returns_failure_even_with_good_notice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, cmd = self._minimal_host_command(root)
            nupkg = root / "demo.nupkg"
            with zipfile.ZipFile(nupkg, "w") as package:
                package.writestr("demo.nuspec", '<package><metadata><id>Demo</id><version>1.0.0</version><license type="expression">MIT</license></metadata></package>')
            good = b"Test-only good licence"
            archive = self._supplement_zip(root, {"Demo/1.0.0": {"notices": [
                self._notice_record("good/LICENSE", good),
                self._notice_record("bad/LICENSE", b"Expected licence")]}},
                {"good/LICENSE": good, "bad/LICENSE": b"Tampered licence"})
            result = subprocess.run(cmd + ["--nupkg", str(nupkg),
                "--supplemental-notices", str(archive), "--out", str(root / "out")],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            saved = json.loads((root / "out/inventory.json").read_text())
            self.assertIn("Supplemental notice hash mismatch: bad/LICENSE", saved["fatalErrors"])
            self.assertEqual(len(next(p for p in saved["packages"] if p["key"] == "Demo/1.0.0")["notices"]), 1)

    def test_supplement_missing_member_and_unsafe_path_fail_closed(self):
        for name, files, error in [
                ("missing/LICENSE", {}, KeyError),
                ("../../escape-LICENSE", {"../../escape-LICENSE": b"Test-only licence"}, ValueError)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                c = m.Collector(root / "out")
                c.records = [{"ecosystem": "NuGet", "key": "Demo/1.0.0", "notices": []}]
                archive = self._supplement_zip(root, {"Demo/1.0.0": {"notices": [
                    self._notice_record(name, b"Test-only licence")]}}, files)
                with self.assertRaises(error):
                    c.supplement(archive)
                self.assertFalse(c.records[0]["notices"])
                self.assertFalse((root / "escape-LICENSE").exists())

    def test_font_audit_requires_exact_published_hash_and_pass_conditions(self):
        cases = [
            ("valid", {}, True),
            ("wrong-hash", {"assemblySha256": m.sha(b"different assembly")}, False),
            ("missing-hash", {"assemblySha256": None}, False),
            ("not-passed", {"status": "failed"}, False),
            ("restricted-payload-remains", {"restrictedOriginalPayloads": 1}, False),
            ("wrong-font", {"replacementFont": "Torus"}, False),
        ]
        for name, changes, accepted in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                host, cmd = self._minimal_host_command(root)
                dll = host / "osu.Game.Resources.dll"
                dll.write_bytes(b"Test-only rebuilt Inter resource assembly")
                audit = {"status": "passed", "restrictedOriginalPayloads": 0,
                         "replacementFont": "Inter", "assemblySha256": m.file_sha(dll)}
                audit.update(changes)
                evidence = root / "audit.json"
                evidence.write_text(json.dumps(audit))
                result = subprocess.run(cmd + ["--resource-font-audit", str(evidence),
                    "--out", str(root / "out")], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0 if accepted else 2, result.stdout + result.stderr)
                saved = json.loads((root / "out/inventory.json").read_text())
                copied = root / "out/Evidence/embedded-font-audit.json"
                replacement = root / "out/FONT-REPLACEMENT.txt"
                if accepted:
                    self.assertFalse(saved["fatalErrors"])
                    self.assertEqual(copied.read_bytes(), evidence.read_bytes())
                    self.assertTrue(replacement.is_file())
                else:
                    self.assertIn("Font audit does not match the published resource assembly", saved["fatalErrors"])
                    self.assertFalse(copied.exists())
                    self.assertFalse(replacement.exists())

    def test_go_queries_only_linked_replacement_module(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            build = root / "build.txt"
            build.write_text("\tdep original/module v1.0.0 h1:test\n\t=> actual/module v2.0.0 h1:test\n")
            module = root / "module"; module.mkdir()
            (module / "LICENSE").write_text("Test-only module licence")
            goroot = root / "goroot"; goroot.mkdir()
            (goroot / "LICENSE").write_text("Test-only runtime licence")
            a = SimpleNamespace(go_build_info=build, go_module_list=None, go_root=goroot, repo=root)
            c = m.Collector(root / "out")
            with patch.object(m.subprocess, "check_output", return_value=json.dumps(
                    {"Path": "actual/module", "Version": "v2.0.0", "Dir": str(module)})) as command:
                m.read_go(a, c)
            self.assertEqual(command.call_args.args[0],
                             [str(goroot / "bin/go"), "list", "-mod=readonly", "-m", "-json", "actual/module@v2.0.0"])
            self.assertFalse(c.errors)
            self.assertEqual(c.records[0]["key"], "actual/module@v2.0.0")

    def test_module_replacement(self):
        self.assertEqual(m.go_dependencies("\tdep old/module v1.0.0 h1:x\n\t=> new/module v2.0.0 h1:y\n"),
                         [{"path": "old/module", "version": "v1.0.0",
                           "replacement": {"path": "new/module", "version": "v2.0.0"}}])

    def test_notice_name_variants(self):
        for name in ["ThirdPartyNotices.txt", "THIRD-PARTY-NOTICES.TXT", "LICENSE", "OFL.txt", "SDL3-LICENSE.txt"]:
            self.assertTrue(m.NOTICE.search(name), name)
        self.assertFalse(m.NOTICE.search("licensedriver.dll"))

    def test_expression_is_not_complete_notice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            package = root / "package"; package.mkdir()
            (package / "p.nuspec").write_text('<package><metadata><id>P</id><version>1</version><license type="expression">MIT</license></metadata></package>')
            c = m.Collector(root / "out")
            c.nuget(folder=package)
            self.assertTrue(any("No readable notice" in gap for gap in c.gaps))

    def test_offline_end_to_end_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); host = root / "host"; host.mkdir()
            nuget = root / "nuget"
            for name, notice in [("demo", "LegalTerms.md"),
                                 ("microsoft.netcore.app.runtime.osx-arm64", "ThirdPartyNotices.txt")]:
                p = nuget / name / "1.0.0"; p.mkdir(parents=True)
                (p / "package.nuspec").write_text('<package><metadata><id>'+name+'</id><version>1.0.0</version><license type="file">'+notice+'</license></metadata></package>')
                (p / notice).write_text("Test-only licence text")
            (host / "host.deps.json").write_text(json.dumps({"libraries": {
                "Demo/1.0.0": {"type": "package"},
                "runtimepack.Microsoft.NETCore.App.Runtime.osx-arm64/1.0.0": {"type": "runtimepack"}}}))
            native = root / "native"; native.mkdir()
            for name in m.REQUIRED_NATIVE:
                (native / name).write_text("Test-only licence")
            goroot = root / "goroot"; goroot.mkdir(); (goroot / "LICENSE").write_text("Test-only Go licence")
            mod = root / "module"; mod.mkdir(); (mod / "LICENSE").write_text("Test-only module licence")
            build = root / "go.txt"; build.write_text("\tdep example.test/module v1.0.0 h1:fixture\n")
            modules = root / "modules.json"; modules.write_text(json.dumps({"Path":"example.test/module","Version":"v1.0.0","Dir":str(mod)}))
            cmd = [sys.executable, str(ROOT / "collect_notices.py"), "--host", str(host),
                   "--nuget-root", str(nuget), "--native-notices", str(native),
                   "--go-build-info", str(build), "--go-module-list", str(modules),
                   "--go-root", str(goroot)]
            def run(out):
                return subprocess.run(cmd + ["--out", str(root / out)], capture_output=True, text=True)
            ok = run("ok"); self.assertEqual(ok.returncode, 0, ok.stderr + ok.stdout)
            inventory = json.loads((root / "ok/inventory.json").read_text())
            self.assertEqual(len(inventory["packages"]), 3)
            self.assertFalse(inventory["fatalErrors"])
            self.assertTrue((root / "ok/NuGet/demo/1.0.0/LegalTerms.md").is_file())
            self.assertTrue((root / "ok/NuGet/microsoft.netcore.app.runtime.osx-arm64/1.0.0/ThirdPartyNotices.txt").is_file())
            (native / "BASS.txt").unlink()
            bad = run("missing"); self.assertEqual(bad.returncode, 2)
            self.assertIn("Missing required native notice: BASS.txt", (root / "missing/INDEX.txt").read_text())
            (native / "BASS.txt").write_text("Test-only licence")
            (host / "libavcodec.58.dylib").write_bytes(b"wrong binary")
            bad = run("wrong-ffmpeg"); self.assertEqual(bad.returncode, 2)
            self.assertIn("FFmpeg binary differs", (root / "wrong-ffmpeg/INDEX.txt").read_text())

    def test_exact_nuget_ffmpeg_manifest(self):
        package = ROOT / "ppy.osu.framework.nativelibs.2025.806.0-nativelibs.nupkg"
        if not package.exists():
            self.skipTest("Research package is optional in CI")
        manifest = json.loads((ROOT / "ffmpeg-notices/SOURCES.json").read_text())
        self.assertEqual(m.sha(package.read_bytes()), manifest["nugetPackageSha256"])
        with zipfile.ZipFile(package) as z:
            for record in manifest["binaries"]:
                data = z.read("runtimes/osx/native/" + record["filename"])
                self.assertEqual(m.sha(data), record["sha256"])
                self.assertTrue(any("LGPL version 2.1 or later" in s for s in m.binary_strings(data)))

if __name__ == "__main__":
    unittest.main()
