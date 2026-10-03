#!/usr/bin/env python3
"""Exercise the relocated distribution on a real Apple Silicon macOS runner."""

import json
import math
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile


def run(*args, **kwargs):
    try:
        return subprocess.run(args, check=True, text=True, timeout=300, **kwargs)
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout, file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        raise


def main():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("Bundle smoke testing requires Apple Silicon macOS")
    repo = Path(__file__).resolve().parent.parent
    original = repo / "dist/build-macos/danser.app"
    evidence = repo / "dist/build-macos/verification"
    evidence.mkdir(parents=True, exist_ok=True)
    run(str(repo / "tools/macos-smoke-fixture.sh"), cwd=repo)
    fixture = repo / ".deps/macos/smoke/Songs/000 macOS Port Smoke Test"
    expected_osu = run("git", "-C", str(repo / "third_party/osu"), "rev-parse", "HEAD",
                       capture_output=True).stdout.strip()
    source_revision = run("git", "-C", str(repo), "rev-parse", "HEAD", capture_output=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="danser relocated bundle ") as temporary:
        root = Path(temporary)
        app = root / "danser.app"
        run("ditto", str(original), str(app))
        run("codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app))
        with (app / "Contents/Info.plist").open("rb") as source:
            info = plistlib.load(source)
        assert info["LSMinimumSystemVersion"] == "15.0"
        binary = app / "Contents/MacOS/danser-cli"
        architecture = run("file", str(binary), capture_output=True).stdout
        assert "Mach-O" in architecture and "arm64" in architecture, architecture
        load_commands = run("otool", "-l", str(binary), capture_output=True).stdout
        assert "@executable_path/../Frameworks" in load_commands
        assert str(repo) not in load_commands, "Executable retains its build-directory rpath"
        (evidence / "load-commands.txt").write_text(load_commands)
        env = dict(os.environ, HOME=str(root / "home"), DOTNET_ROOT=str(root / "no-dotnet"),
                   DOTNET_ROOT_ARM64=str(root / "no-dotnet"), DOTNET_MULTILEVEL_LOOKUP="0")
        Path(env["HOME"]).mkdir()
        settings = Path(env["HOME"]) / "Library/Application Support/danser/settings"
        settings.mkdir(parents=True)
        # LoadConfig starts from defaults. An existing empty config ensures the
        # CLI patch is applied before the first beatmap database scan.
        (settings / "default.json").write_text("{}\n")
        for key in ("DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "DANSER_MACOS_DEPS_DIR"):
            env.pop(key, None)
        host = app / "Contents/MacOS/lazer-rules-host/danser-lazer-rules"
        env["DANSER_LAZER_DIAGNOSTICS"] = "1"
        response_file = evidence / "rules-host-rejudge.json"
        with response_file.open("w") as output, (evidence / "rules-host.log").open("w") as log:
            process = subprocess.Popen([str(host), "rejudge", "--beatmap", str(fixture / "macos-smoke.osu"),
                                        "--replay", str(fixture / "macos-smoke.osr")],
                                       env=env, stdout=output, stderr=log)
            try:
                process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                try:
                    subprocess.run(["sample", str(process.pid), "5", "-file", str(evidence / "rules-host-sample.txt")],
                                   timeout=30, check=False)
                except subprocess.SubprocessError as error:
                    print(f"Process sampling failed: {error}", file=sys.stderr)
                try:
                    process.wait(timeout=180)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise RuntimeError("Rules host timed out; see rules-host.log and rules-host-sample.txt")
            assert process.returncode == 0, "Rules host failed; see rules-host.log"
        response = json.loads(response_file.read_text())
        assert response["protocolVersion"] == 3
        assert response["engine"]["osuSourceRevision"] == expected_osu
        assert response["replay"]["frameCount"] == 4687
        judgements = response["judgements"]
        assert judgements and all(a["judgedAt"] <= b["judgedAt"]
                                  for a, b in zip(judgements, judgements[1:]))
        for key in ("performance", "fullComboPerformance", "perfectPerformance"):
            assert math.isfinite(response["rejudged"][key]["total"])
        patch = json.dumps({
            "General": {"OsuSongsDir": str(fixture.parent)},
            "Graphics": {"Fullscreen": False, "WindowWidth": 640, "WindowHeight": 360,
                         "Experimental": {"UsePersistentBuffers": True}},
            "Recording": {"FrameWidth": 640, "FrameHeight": 360, "FPS": 30,
                          "OutputDir": str(evidence), "Encoder": "libx264",
                          "libx264": {"Preset": "ultrafast"}},
        })
        common = [str(binary), "-noupdatecheck", "-replay=" + str(fixture / "macos-smoke.osr"),
                  "-sPatch=" + patch, "-quickstart"]
        with (evidence / "screenshot.log").open("w") as log:
            run(*common, "-ss=20", "-out=ci-smoke", env=env, stdout=log, stderr=subprocess.STDOUT)
        screenshot = Path(env["HOME"]) / "Library/Application Support/danser/screenshots/ci-smoke.png"
        assert screenshot.is_file() and screenshot.stat().st_size > 1000
        shutil.copy2(screenshot, evidence / "ci-smoke.png")
        with (evidence / "recording.log").open("w") as log:
            run(*common, "-record", "-start=20", "-end=23", "-out=ci-smoke", env=env,
                stdout=log, stderr=subprocess.STDOUT)
        video = evidence / "ci-smoke.mp4"
        probe = run("ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                    str(video), capture_output=True)
        media = json.loads(probe.stdout)
        assert float(media["format"]["duration"]) >= 3
        assert any(s["codec_type"] == "video" and s["width"] == 640 and s["height"] == 360
                   for s in media["streams"])
        assert any(s["codec_type"] == "audio" for s in media["streams"])
        run("ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-")
        (evidence / "ffprobe.json").write_text(probe.stdout)
        run("codesign", "--verify", "--deep", "--strict", str(app))
    provenance = {
        "sourceRevision": source_revision,
        "osuSourceRevision": expected_osu,
        "platform": "macOS arm64",
        "minimumMacOS": "15.0",
        "runnerMacOS": platform.mac_ver()[0],
        "workflowRun": os.environ.get("GITHUB_SERVER_URL", "https://github.com") + "/" +
            os.environ.get("GITHUB_REPOSITORY", "Chesszyh/danser-go") + "/actions/runs/" +
            os.environ.get("GITHUB_RUN_ID", "local"),
        "checks": ["native Go/OpenGL regressions (previous workflow step)", "relocated app signature",
                   "self-contained rules-host rejudgement", "replay screenshot", "video/audio recording decode"],
        "limitations": ["ad-hoc signed, not Developer ID signed or notarized", "external FFmpeg CLI required",
                        "physical Retina/display transitions, interactive launcher lifecycle and thermal behaviour untested"],
    }
    (evidence.parent / "build-info.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Relocated bundle: architecture, signature, self-contained replay rejudgement, screenshot and recording passed")
    print("Physical Retina/display transitions, interactive launcher lifecycle and thermal behaviour are not tested here")


if __name__ == "__main__":
    main()
