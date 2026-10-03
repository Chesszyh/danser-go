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
                             ["go", "list", "-mod=readonly", "-m", "-json", "actual/module@v2.0.0"])
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
