#!/usr/bin/env python3
"""Publish only the verified, explicitly authorized macOS preview from Actions.

Requires contents:write, the master-push workflow gate, and serialized publishers.
Failures leave a draft for inspection; nothing is overwritten or deleted.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

REPOSITORY = "Chesszyh/danser-go"
TAG = "macos-2026.10.03"
ASSETS = ("danser-macos.zip", "danser-macos-source.tar.gz",
          "danser-macos-source-manifest.json", "build-info.json", "SHA256SUMS")
CHECKS = {"native Go/OpenGL regressions (previous workflow step)", "relocated app signature",
          "embedded Inter font replacement audit", "self-contained rules-host rejudgement",
          "live rules-host frame/finish protocol", "replay screenshot", "video/audio recording decode"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def validate(directory, sha, run_id):
    require(re.fullmatch(r"[0-9a-f]{40}", sha), "GITHUB_SHA must be an exact commit SHA")
    require(re.fullmatch(r"[0-9]+", run_id), "GITHUB_RUN_ID must be numeric")
    for name in ASSETS:
        path = directory / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0,
                "Missing, linked, or empty asset: " + name)
    expected = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *]([^/\\]+)", line)
        require(match is not None, "Malformed SHA256SUMS entry")
        checksum, name = match.groups()
        require(name in ASSETS[:-1] and name not in expected, "Unexpected or duplicate checksum asset")
        expected[name] = checksum
    require(set(expected) == set(ASSETS[:-1]), "SHA256SUMS must cover all four payloads")
    hashes = {name: digest(directory / name) for name in ASSETS}
    require(all(hashes[name] == value for name, value in expected.items()), "Asset checksum mismatch")
    info = json.loads((directory / "build-info.json").read_text())
    require(info["sourceRevision"] == sha, "Build source revision mismatch")
    require(info["workflowRun"] == f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
            "Build workflow run mismatch")
    require(info["platform"] == "macOS arm64" and info["minimumMacOS"] == "15.0"
            and info["runnerMacOS"].startswith("15."), "Unexpected platform or macOS version")
    require(CHECKS <= set(info["checks"]), "Required smoke checks are missing")
    fonts = info["resourceFonts"]
    require(fonts["status"] == "passed" and fonts["replacementFont"] == "Inter"
            and type(fonts["restrictedOriginalPayloads"]) is int and fonts["restrictedOriginalPayloads"] == 0
            and fonts["replacementDescriptors"] == 11 and fonts["replacementPages"] == 39,
            "Embedded Inter font audit did not pass")
    manifest_bytes = (directory / "danser-macos-source-manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest["schemaVersion"] == 1 and manifest["application"]["commit"] == sha
            and manifest["buildInfo"] == info, "Source manifest/build mismatch")
    require(manifest["optionalRulesHostIncluded"] is True, "Full rules host is required")
    audit = manifest["modifiedResources"]["sourceAudit"]
    require(audit["status"] == "passed" and type(audit["restricted_original_payloads"]) is int
            and audit["restricted_original_payloads"] == 0
            and audit["source_commit"] == fonts["sourceRevision"], "Modified resource source audit mismatch")
    with tarfile.open(directory / "danser-macos-source.tar.gz", "r:gz") as archive:
        member = archive.getmember("danser-macos-source/source-manifest.json")
        require(member.isfile() and member.size == len(manifest_bytes), "Missing archived source manifest")
        require(archive.extractfile(member).read() == manifest_bytes, "Archived source manifest differs")
    return info, hashes


def gh(*args, **kwargs):
    return subprocess.run(["gh", *args], check=True, stderr=subprocess.PIPE, timeout=1800, **kwargs)


def api(endpoint, *, method="GET", payload=None, missing=False, paginate=False):
    args = ["api", "--hostname", "github.com", "--method", method, endpoint]
    if paginate:
        args += ["--paginate", "--slurp"]
    if payload is not None:
        args += ["--input", "-"]
    try:
        result = gh(*args, input=json.dumps(payload) if payload is not None else None,
                    stdout=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as error:
        if missing and method == "GET" and "(HTTP 404)" in (error.stderr or ""):
            return None
        raise
    return json.loads(result.stdout)


def verify_tag(prefix, sha, allow_missing=False):
    ref = api(f"{prefix}/git/ref/tags/{TAG}", missing=allow_missing)
    if ref is None:
        return
    target = ref["object"]
    for _ in range(10):
        if target["type"] != "tag":
            break
        target = api(f"{prefix}/git/tags/{target['sha']}")["object"]
    require(target["type"] == "commit" and target["sha"] == sha, "Release tag targets a different commit")


def release_notes(info, hashes):
    sha = info["sourceRevision"]
    return f"""Apple Silicon macOS 15+ preview, with the full self-contained osu!lazer rules host built from the pinned upstream source.

Restricted Torus/Torus Alternate/Venera font payloads have been replaced with SIL OFL 1.1 Inter compatibility resources. Source and embedded-resource audits passed; glyph metrics may differ from the original fonts.

Verified on a macOS 15 arm64 runner: native Go/OpenGL regressions, relocated app signature and self-contained rejudgement, live rules-host frame/finish protocol, replay screenshot, and video/audio recording decode.

The app is ad-hoc signed, not Developer ID signed or notarized. Recording requires an external FFmpeg CLI. Physical Retina/display transitions, interactive launcher lifecycle, and thermal behaviour remain untested.

Download danser-macos.zip for the app. The source archive, standalone source manifest, build-info.json, and SHA256SUMS provide matching source, provenance, and checksums. Source rebuild instructions and applicable third-party licences/notices are included; this is not a promise of bit-identical rebuilds or comprehensive rights clearance. This is a free non-commercial preview; third-party licence rights and proprietary BASS terms remain applicable.

Source: https://github.com/{REPOSITORY}/commit/{sha}
Verification run: {info['workflowRun']}

<!-- danser-macos-publisher:{REPOSITORY}:{sha}:{hashes['SHA256SUMS']} -->
"""


def check_release(release, sha, body):
    require(release["draft"] is True, "An existing published release will not be changed")
    require(release["tag_name"] == TAG and release["target_commitish"] == sha
            and release["body"] == body and release["prerelease"] is True
            and release["author"]["login"] == "github-actions[bot]",
            "Draft is not owned by this verified build")


def verify_assets(release, directory, hashes, complete=False):
    assets = release["assets"]
    names = [asset["name"] for asset in assets]
    require(len(names) == len(set(names)) and set(names) <= set(ASSETS), "Unexpected release assets")
    require(not complete or set(names) == set(ASSETS), "Release assets are incomplete")
    with tempfile.TemporaryDirectory(prefix="verify-macos-release-") as temporary:
        for asset in assets:
            name = asset["name"]
            require(asset["state"] == "uploaded" and asset["size"] == (directory / name).stat().st_size,
                    "Remote asset state/size mismatch: " + name)
            downloaded = Path(temporary) / name
            with downloaded.open("wb") as output:
                gh("api", "--hostname", "github.com", "-H", "Accept: application/octet-stream",
                   f"repos/{REPOSITORY}/releases/assets/{int(asset['id'])}", stdout=output)
            require(digest(downloaded) == hashes[name], "Downloaded asset checksum mismatch: " + name)
    return set(names)


def publish(directory, sha, run_id):
    info, hashes = validate(directory, sha, run_id)  # All local gates precede any writes.
    prefix = f"repos/{REPOSITORY}"
    body = release_notes(info, hashes)
    require(api(f"{prefix}/commits/{sha}")["sha"] == sha, "Commit is not present on GitHub")
    releases = [r for page in api(f"{prefix}/releases?per_page=100", paginate=True) for r in page
                if r["tag_name"] == TAG]
    require(len(releases) <= 1, "Multiple releases use the authorized tag")
    verify_tag(prefix, sha, allow_missing=True)
    if releases:
        release = releases[0]
        check_release(release, sha, body)
    else:
        release = api(f"{prefix}/releases", method="POST", payload={
            "tag_name": TAG, "target_commitish": sha, "name": "macOS Inter preview (Apple Silicon)",
            "body": body, "draft": True, "prerelease": True, "make_latest": "false"})
        check_release(release, sha, body)
    present = verify_assets(release, directory, hashes)
    missing = [str((directory / name).resolve()) for name in ASSETS if name not in present]
    if missing:
        gh("release", "upload", TAG, "--repo", f"github.com/{REPOSITORY}", *missing, stdout=subprocess.PIPE)
    endpoint = f"{prefix}/releases/{int(release['id'])}"
    ready = api(endpoint)
    check_release(ready, sha, body)
    verify_assets(ready, directory, hashes, complete=True)
    verify_tag(prefix, sha, allow_missing=True)
    api(endpoint, method="PATCH", payload={"draft": False, "prerelease": True, "make_latest": "false"})
    published = api(endpoint)
    require(published["draft"] is False and published["prerelease"] is True
            and published["tag_name"] == TAG and published["target_commitish"] == sha
            and published["body"] == body, "Published release metadata differs")
    verify_tag(prefix, sha)
    verify_assets(published, directory, hashes, complete=True)
    print(f"Verified prerelease: https://github.com/{REPOSITORY}/releases/tag/{TAG}")


def main():
    require(len(sys.argv) == 2, "Usage: publish-macos-release.py ARTIFACT_DIRECTORY")
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "Unexpected release repository")
    require(os.environ.get("GITHUB_EVENT_NAME") == "push" and os.environ.get("GITHUB_REF") == "refs/heads/master",
            "Publishing requires the authorized master-push workflow")
    require(os.environ.get("GH_TOKEN"), "GH_TOKEN is required")
    publish(Path(sys.argv[1]).resolve(), os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"])


if __name__ == "__main__":
    main()
