#!/usr/bin/env python3
"""Exercise the relocated distribution on a real Apple Silicon macOS runner."""

import json
import math
import os
from pathlib import Path
import platform
import plistlib
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time


def run(*args, **kwargs):
    try:
        return subprocess.run(args, check=True, text=True, timeout=300, **kwargs)
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout, file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        raise


def verify_rejudge(response, expected_osu, object_count):
    assert response["protocolVersion"] == 3
    assert response["engine"]["osuSourceRevision"] == expected_osu
    assert response["replay"]["frameCount"] == 4687
    judgements = response["judgements"]
    assert {event["objectIndex"] for event in judgements} == set(range(object_count))
    # TimeAbsolute is clamped separately for each osu! hit object. Spinner
    # callbacks can therefore move backwards slightly; keep callback/snapshot
    # order intact rather than sorting or requiring monotonic timestamps.
    for event in judgements:
        assert all(math.isfinite(event[key]) for key in ("judgedAt", "hitError", "objectEndTime"))
        assert 0 <= event["judgedAt"] <= 80_000
        assert abs(event["judgedAt"] - event["objectEndTime"] - event["hitError"]) < 0.00001
    for key in ("performance", "fullComboPerformance", "perfectPerformance"):
        assert math.isfinite(response["rejudged"][key]["total"])


def verify_live(host, beatmap, env, evidence, expected_osu, object_count):
    messages = queue.Queue()
    deadline = time.monotonic() + 180
    with (evidence / "rules-host-live.log").open("w") as errors, \
            (evidence / "rules-host-live.jsonl").open("w") as transcript:
        process = subprocess.Popen([str(host), "live", "--beatmap", str(beatmap),
                                    "--mods-json", '[{"acronym":"NF"}]'], env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, bufsize=1)

        def read_output():
            for line in process.stdout:
                messages.put(line)
            messages.put(None)

        threading.Thread(target=read_output, daemon=True).start()

        def receive():
            remaining = deadline - time.monotonic()
            assert remaining > 0, "Live host exceeded its total timeout"
            line = messages.get(timeout=min(60, remaining))
            assert line is not None, "Live host closed before completing the protocol"
            transcript.write(line); transcript.flush()
            message = json.loads(line)
            assert message["protocolVersion"] == 3
            assert message["type"] != "error", message.get("message")
            return message

        def send(message):
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()

        try:
            ready = receive()
            assert ready["type"] == "ready" and ready["engine"]["osuSourceRevision"] == expected_osu
            covered = set()
            final_object_judged = False
            for frame_id, position in enumerate(range(0, 75_001, 50)):
                send({"type": "frame", "frameId": frame_id, "time": position,
                      "x": 256, "y": 192, "left": False, "right": False, "smoke": False})
                result = receive()
                assert result["type"] == "frame" and result["frameId"] == frame_id
                for judgement in result.get("judgements") or []:
                    covered.add(judgement["objectIndex"])
                    if judgement["objectIndex"] == object_count - 1 and judgement["objectPart"] == "spinner":
                        final_object_judged = True
                if final_object_judged:
                    break
            assert covered == set(range(object_count)) and final_object_judged
            send({"type": "finish", "frameId": frame_id + 1, "time": position,
                  "x": 256, "y": 192, "left": False, "right": False, "smoke": False})
            process.stdin.close()
            complete = receive()
            assert complete["type"] == "complete"
            for key in ("performance", "fullComboPerformance", "perfectPerformance"):
                assert math.isfinite(complete["score"][key]["total"])
            process.wait(timeout=30)
            assert process.returncode == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


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
        font_dir = app / "Contents/Resources/LazerFonts"
        audit = run(str(host), "audit-fonts", str(font_dir / "OPEN_FONT_PROVENANCE.json"),
                    str(font_dir / "pinned-resource-lock.json.gz"), env=env, capture_output=True)
        font_report = json.loads(audit.stdout)
        assert font_report["status"] == "passed" and font_report["restrictedOriginalPayloads"] == 0
        (evidence / "embedded-font-audit.json").write_text(audit.stdout)
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
        object_lines = (fixture / "macos-smoke.osu").read_text().split("[HitObjects]", 1)[1].splitlines()
        object_count = sum(bool(line.strip()) and not line.startswith("//") for line in object_lines)
        verify_rejudge(response, expected_osu, object_count)
        verify_live(host, fixture / "macos-smoke.osu", env, evidence, expected_osu, object_count)
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
                   "embedded Inter font replacement audit", "self-contained rules-host rejudgement",
                   "live rules-host frame/finish protocol", "replay screenshot", "video/audio recording decode"],
        "resourceFonts": font_report,
        "limitations": ["ad-hoc signed, not Developer ID signed or notarized", "external FFmpeg CLI required",
                        "physical Retina/display transitions, interactive launcher lifecycle and thermal behaviour untested"],
    }
    (evidence.parent / "build-info.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Relocated bundle: architecture, signature, self-contained replay rejudgement, screenshot and recording passed")
    print("Physical Retina/display transitions, interactive launcher lifecycle and thermal behaviour are not tested here")


if __name__ == "__main__":
    main()
