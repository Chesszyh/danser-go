#!/usr/bin/env python3
"""Offline release gates and resumable publication tests; no GitHub writes."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("publisher", Path(__file__).with_name("publish-macos-release.py"))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
SHA = "a" * 40
RUN_ID = "1234"


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.info = {
            "sourceRevision": SHA, "workflowRun": f"https://github.com/{p.REPOSITORY}/actions/runs/{RUN_ID}",
            "platform": "macOS arm64", "minimumMacOS": "15.0", "runnerMacOS": "15.7",
            "checks": sorted(p.CHECKS), "resourceFonts": {
                "status": "passed", "replacementFont": "Inter", "restrictedOriginalPayloads": 0,
                "replacementDescriptors": 11, "replacementPages": 39, "sourceRevision": "b" * 40}}
        self.manifest = {"schemaVersion": 1, "application": {"commit": SHA}, "buildInfo": self.info,
                         "optionalRulesHostIncluded": True, "modifiedResources": {"sourceAudit": {
                             "status": "passed", "restricted_original_payloads": 0, "source_commit": "b" * 40}}}
        self.write_fixture()
        self.remote = None
        self.tag_sha = None
        self.asset_bytes = {}
        self.writes = []
        self.calls = []
        self.corrupt_download = False

    def checksums(self):
        (self.directory / "SHA256SUMS").write_text("".join(
            f"{p.digest(self.directory / name)}  {name}\n" for name in p.ASSETS[:-1]))

    def write_fixture(self):
        (self.directory / "danser-macos.zip").write_bytes(b"synthetic app archive")
        (self.directory / "build-info.json").write_text(json.dumps(self.info))
        manifest = json.dumps(self.manifest).encode()
        (self.directory / "danser-macos-source-manifest.json").write_bytes(manifest)
        with tarfile.open(self.directory / "danser-macos-source.tar.gz", "w:gz") as archive:
            member = tarfile.TarInfo("danser-macos-source/source-manifest.json")
            member.size = len(manifest)
            archive.addfile(member, io.BytesIO(manifest))
        self.checksums()

    def owned_draft(self):
        info, hashes = p.validate(self.directory, SHA, RUN_ID)
        return {"id": 42, "tag_name": p.TAG, "target_commitish": SHA,
                "draft": True, "prerelease": True, "body": p.release_notes(info, hashes),
                "author": {"login": "github-actions[bot]"}, "assets": []}

    def upload(self, name):
        data = (self.directory / name).read_bytes()
        asset_id = len(self.asset_bytes) + 1
        self.asset_bytes[asset_id] = data
        self.remote["assets"].append({"id": asset_id, "name": name, "size": len(data), "state": "uploaded"})

    def fake_run(self, command, **kwargs):
        self.calls.append(command)
        self.assertTrue(kwargs["check"])
        self.assertNotIn("shell", kwargs)
        self.assertNotIn("--clobber", command)
        if command[1:3] == ["release", "upload"]:
            self.writes.append(("UPLOAD", command[6:]))
            for path in command[6:]:
                self.upload(Path(path).name)
            return subprocess.CompletedProcess(command, 0, stdout=b"")
        self.assertEqual(command[1], "api")
        endpoint = command[6]
        if "--method" not in command:
            data = self.asset_bytes[int(endpoint.rsplit("/", 1)[1])]
            kwargs["stdout"].write(b"corrupted" if self.corrupt_download else data)
            return subprocess.CompletedProcess(command, 0)
        method = command[5]
        payload = json.loads(kwargs["input"]) if kwargs.get("input") else None
        if method != "GET":
            self.writes.append((method, copy.deepcopy(payload)))
        if "/commits/" in endpoint:
            result = {"sha": SHA}
        elif "/git/ref/" in endpoint:
            if self.tag_sha is None:
                raise subprocess.CalledProcessError(1, command, stderr="gh: Not Found (HTTP 404)")
            result = {"object": {"type": "commit", "sha": self.tag_sha}}
        elif endpoint.endswith("?per_page=100"):
            self.assertIn("--paginate", command)
            self.assertIn("--slurp", command)
            result = [[self.remote] if self.remote else []]
        elif method == "POST":
            self.remote = {**payload, "id": 42, "author": {"login": "github-actions[bot]"}, "assets": []}
            result = self.remote
        elif method == "PATCH":
            self.assertEqual(set(self.asset_bytes), set(range(1, 6)))
            self.remote.update(payload)
            self.tag_sha = self.remote["target_commitish"]
            result = self.remote
        else:
            result = self.remote
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(result))

    def publish(self):
        with patch.object(p.subprocess, "run", self.fake_run), patch("builtins.print"):
            p.publish(self.directory, SHA, RUN_ID)

    def test_fresh_release_is_draft_verified_then_published(self):
        self.publish()
        self.assertEqual([method for method, _ in self.writes], ["POST", "UPLOAD", "PATCH"])
        create = self.writes[0][1]
        self.assertTrue(create["draft"])
        self.assertEqual(create["target_commitish"], SHA)
        self.assertEqual(create["make_latest"], "false")
        self.assertEqual(self.writes[-1][1], {"draft": False, "prerelease": True, "make_latest": "false"})
        self.assertEqual({Path(x).name for x in self.writes[1][1]}, set(p.ASSETS))
        downloads = [c for c in self.calls if "Accept: application/octet-stream" in c]
        self.assertEqual(len(downloads), 10)  # Full bytes verified before and after publication.
        self.assertEqual(self.tag_sha, SHA)

    def test_owned_partial_draft_resumes_without_overwriting(self):
        self.remote = self.owned_draft()
        self.upload(p.ASSETS[0])
        self.publish()
        self.assertEqual([method for method, _ in self.writes], ["UPLOAD", "PATCH"])
        self.assertEqual({Path(x).name for x in self.writes[0][1]}, set(p.ASSETS[1:]))

    def test_published_release_is_never_changed(self):
        self.remote = self.owned_draft()
        self.remote["draft"] = False
        with self.assertRaisesRegex(ValueError, "published release"):
            self.publish()
        self.assertEqual(self.writes, [])

    def test_foreign_or_different_build_draft_is_never_changed(self):
        for key, value in (("target_commitish", "c" * 40), ("body", "foreign draft"),
                           ("author", {"login": "another-owner"}), ("prerelease", False)):
            with self.subTest(key=key):
                self.remote = self.owned_draft()
                self.remote[key] = value
                with self.assertRaisesRegex(ValueError, "not owned"):
                    self.publish()
                self.assertEqual(self.writes, [])

    def test_wrong_tag_commit_stops_before_writes(self):
        self.tag_sha = "d" * 40
        with self.assertRaisesRegex(ValueError, "different commit"):
            self.publish()
        self.assertEqual(self.writes, [])

    def test_corrupt_download_keeps_release_draft(self):
        self.corrupt_download = True
        with self.assertRaisesRegex(ValueError, "Downloaded asset checksum"):
            self.publish()
        self.assertTrue(self.remote["draft"])
        self.assertNotIn("PATCH", [method for method, _ in self.writes])

    def test_unexpected_or_unfinished_assets_block_resume(self):
        for bad_asset in ({"name": "unexpected.txt"}, {"name": p.ASSETS[0], "state": "starter", "size": 0}):
            with self.subTest(asset=bad_asset):
                self.remote = self.owned_draft()
                self.remote["assets"] = [bad_asset]
                with self.assertRaises(ValueError):
                    self.publish()
                self.assertEqual(self.writes, [])

    def test_invalid_build_metadata_is_rejected_before_network(self):
        original = copy.deepcopy(self.info)
        changes = (("sourceRevision", "c" * 40), ("workflowRun", "https://example.invalid"),
                   ("platform", "macOS x86_64"), ("minimumMacOS", "14.0"),
                   ("runnerMacOS", "14.7"), ("checks", []))
        for key, value in changes:
            with self.subTest(key=key):
                self.info = {**original, key: value}
                self.write_fixture()
                with patch.object(p, "gh") as gh, self.assertRaises(ValueError):
                    p.publish(self.directory, SHA, RUN_ID)
                gh.assert_not_called()

    def test_failed_or_wrong_font_replacement_is_rejected(self):
        original = copy.deepcopy(self.info["resourceFonts"])
        for key, value in (("status", "failed"), ("replacementFont", "Torus"),
                           ("restrictedOriginalPayloads", 1), ("restrictedOriginalPayloads", False),
                           ("replacementDescriptors", 10), ("replacementPages", 38)):
            with self.subTest(key=key, value=value):
                self.info["resourceFonts"] = {**original, key: value}
                self.write_fixture()
                with self.assertRaisesRegex(ValueError, "Inter font audit"):
                    p.validate(self.directory, SHA, RUN_ID)

    def test_checksums_reject_corruption_missing_duplicate_and_traversal(self):
        checksum_path = self.directory / "SHA256SUMS"
        good = checksum_path.read_text()
        variants = (good.replace(good[:64], "0" * 64), "\n".join(good.splitlines()[:-1]),
                    good + good.splitlines()[0] + "\n", good.replace(p.ASSETS[0], "../" + p.ASSETS[0]))
        for value in variants:
            with self.subTest(value=value[:70]):
                checksum_path.write_text(value)
                with self.assertRaises(ValueError):
                    p.validate(self.directory, SHA, RUN_ID)

    def test_missing_full_host_and_modified_source_fail(self):
        self.manifest["optionalRulesHostIncluded"] = False
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "Full rules host"):
            p.validate(self.directory, SHA, RUN_ID)
        self.manifest["optionalRulesHostIncluded"] = True
        self.manifest["modifiedResources"]["sourceAudit"]["restricted_original_payloads"] = 1
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "source audit"):
            p.validate(self.directory, SHA, RUN_ID)

    def test_source_archive_manifest_must_match(self):
        self.manifest["extra"] = "only standalone manifest changed"
        (self.directory / "danser-macos-source-manifest.json").write_text(json.dumps(self.manifest))
        self.checksums()
        with self.assertRaisesRegex(ValueError, "archived source manifest"):
            p.validate(self.directory, SHA, RUN_ID)

    def test_http_errors_are_not_mistaken_for_missing_release(self):
        error = subprocess.CalledProcessError(1, ["gh"], stderr="gh: Forbidden (HTTP 403)")
        with patch.object(p, "gh", side_effect=error), self.assertRaises(subprocess.CalledProcessError):
            p.api("repos/example/repo/git/ref/tags/tag", missing=True)

    def test_main_requires_approved_repo_and_master_push(self):
        env = {"GITHUB_REPOSITORY": p.REPOSITORY, "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/master",
               "GITHUB_SHA": SHA, "GITHUB_RUN_ID": RUN_ID, "GH_TOKEN": "synthetic-test-token"}
        for key, value in (("GITHUB_REPOSITORY", "another/repo"), ("GITHUB_EVENT_NAME", "pull_request"),
                           ("GITHUB_REF", "refs/heads/another"), ("GH_TOKEN", "")):
            with self.subTest(key=key), patch.dict(os.environ, {**env, key: value}, clear=True), \
                    patch.object(p.sys, "argv", ["publisher", str(self.directory)]), \
                    patch.object(p, "publish") as publish, self.assertRaises(ValueError):
                p.main()
            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
