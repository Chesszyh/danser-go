#!/usr/bin/env python3
"""Pinned, deterministic Inter compatibility fonts; Python standard library only.

Usage: python replace_restricted_fonts.py {preflight,apply,audit,scan} CHECKOUT_OR_DIRECTORY
The adjacent pinned-resource-lock.json is required and authenticated by SHA-256.
apply changes the explicitly supplied checkout; this script never downloads or builds.
scan detects whole-file original restricted payloads, including renamed copies. Extract
assembly resources first: scanning a DLL as one file does not inspect embedded resources.
"""
from __future__ import annotations

import argparse
import hashlib
import gzip
import json
import shutil
import struct
import sys
import tempfile
from pathlib import Path

COMMIT = "742ca60d4e7273dce0cac2fced7cd132f26f11c8"
LOCK_SHA256 = "1ca193dfe0510c2c88ee3d6732b0c187447dc6233262df9b97fd85fb8c08423f"
PROJECT = "osu.Game.Resources"
RESTRICTED = ("Torus", "Torus-Alternate", "Venera")
NOTICE_PATH = "Fonts/OPEN_FONT_SUBSTITUTIONS.txt"
MANIFEST_PATH = "Fonts/OPEN_FONT_PROVENANCE.json"
MAPPINGS = tuple(
    (family, weight, weight, ".fnt" if family == "Torus-Alternate" else ".bin")
    for family in ("Torus", "Torus-Alternate")
    for weight in ("Light", "Regular", "SemiBold", "Bold")
) + (("Venera", "Light", "Light", ".bin"),
     ("Venera", "Bold", "Bold", ".bin"),
     ("Venera", "Black", "Bold", ".bin"))


class ValidationError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def canonical_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_lock(path: Path | None = None) -> dict:
    path = path or Path(__file__).with_name("pinned-resource-lock.json.gz")
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    if sha256(data) != LOCK_SHA256:
        raise ValidationError("Pinned resource lock checksum mismatch")
    lock = json.loads(data)
    if lock.get("commit") != COMMIT:
        raise ValidationError("Unexpected pinned resource revision")
    return lock


def resource_project(checkout: Path) -> Path:
    if checkout.is_symlink():
        raise ValidationError("Checkout must not be a symlink")
    project = checkout / PROJECT
    if not project.is_dir() or project.is_symlink():
        raise ValidationError(f"Expected a source checkout containing {PROJECT}/")
    return project


def files_under(directory: Path) -> dict[str, Path]:
    files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValidationError(f"Symlink is not allowed: {path}")
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = path
        elif not path.is_dir():
            raise ValidationError(f"Non-regular path is not allowed: {path}")
    return files


def verify_bytes(path: str, data: bytes, entry: dict) -> None:
    if len(data) != entry["size"] or git_blob_sha1(data) != entry["git_blob_sha1"]:
        raise ValidationError(f"Pinned source hash mismatch: {path}")


def project_pins(lock: dict) -> dict:
    prefix = PROJECT + "/"
    return {p[len(prefix):]: entry for p, entry in lock["files"].items() if p.startswith(prefix)}


def restricted_path(path: str) -> bool:
    return any(path.startswith("Fonts/" + name + "/") for name in RESTRICTED)


def payload_path(path: str) -> bool:
    return restricted_path(path) and Path(path).suffix.lower() in (".bin", ".fnt", ".png")


def verify_pristine(checkout: Path, lock: dict) -> None:
    project = resource_project(checkout)
    found = files_under(project)
    expected = project_pins(lock)
    if set(found) != set(expected):
        raise ValidationError("Source file inventory differs from pinned checkout: " +
                              json.dumps({"missing": sorted(set(expected) - set(found)),
                                          "extra": sorted(set(found) - set(expected))}))
    for name, path in found.items():
        verify_bytes(PROJECT + "/" + name, path.read_bytes(), expected[name])
    for name, entry in lock["files"].items():
        if not name.startswith(PROJECT + "/"):
            path = checkout / name
            if path.is_symlink():
                raise ValidationError(f"Symlink is not allowed: {path}")
            verify_bytes(name, path.read_bytes(), entry)


def parse_bmfont(data: bytes) -> list[tuple[int, bytes]]:
    if data[:4] != b"BMF\x03":
        raise ValidationError("Expected BMFont binary version 3")
    blocks, position, seen = [], 4, set()
    while position < len(data):
        if len(data) - position < 5:
            raise ValidationError("Truncated BMFont block header")
        kind, size = struct.unpack_from("<BI", data, position)
        position += 5
        if kind not in (1, 2, 3, 4, 5) or kind in seen:
            raise ValidationError("Unknown or duplicate BMFont block")
        if size > len(data) - position:
            raise ValidationError("Truncated BMFont block")
        blocks.append((kind, data[position:position + size]))
        seen.add(kind)
        position += size
    if not {1, 2, 3, 4}.issubset(seen):
        raise ValidationError("BMFont lacks required blocks")
    by_kind = dict(blocks)
    if len(by_kind[1]) < 15 or not by_kind[1].endswith(b"\0"):
        raise ValidationError("Invalid BMFont info block")
    if len(by_kind[2]) != 15:
        raise ValidationError("Invalid BMFont common block")
    page_count = struct.unpack_from("<H", by_kind[2], 8)[0]
    names = by_kind[3].split(b"\0")
    if not page_count or names[-1] != b"" or len(names) != page_count + 1 or any(not n for n in names[:-1]):
        raise ValidationError("BMFont page count and names disagree")
    if len(set(map(len, names[:-1]))) != 1:
        raise ValidationError("BMFont page names must have equal lengths")
    if len(by_kind[4]) % 20 or len(by_kind.get(5, b"")) % 10:
        raise ValidationError("Invalid BMFont character/kerning block length")
    ids = set()
    width, height = struct.unpack_from("<HH", by_kind[2], 4)
    for offset in range(0, len(by_kind[4]), 20):
        record = by_kind[4][offset:offset + 20]
        codepoint, x, y, w, h, _, _, _, page, channel = struct.unpack("<IHHHHhhhBB", record)
        if codepoint in ids or codepoint > 0x10FFFF:
            raise ValidationError("Duplicate/invalid character id")
        if page >= page_count or x + w > width or y + h > height or channel > 15:
            raise ValidationError("Invalid BMFont glyph page/bounds/channel")
        ids.add(codepoint)
    return blocks


def serialise_bmfont(blocks: list[tuple[int, bytes]]) -> bytes:
    return b"BMF\x03" + b"".join(struct.pack("<BI", kind, len(data)) + data for kind, data in blocks)


def characters(blocks: list[tuple[int, bytes]]) -> dict[int, bytes]:
    data = dict(blocks)[4]
    return {struct.unpack_from("<I", data, p)[0]: data[p:p + 20] for p in range(0, len(data), 20)}


def make_compatible(source: bytes, stem: str, add_narrow_space: bool) -> bytes:
    if not stem or any(c in stem for c in "/\\\0"):
        raise ValidationError("Invalid compatibility resource stem")
    blocks = parse_bmfont(source)
    count = struct.unpack_from("<H", dict(blocks)[2], 8)[0]
    page_names = b"".join(f"{stem}_{i:0{len(str(count - 1))}d}.png".encode("ascii") + b"\0" for i in range(count))
    records = characters(blocks)
    if add_narrow_space and 0x202F not in records:
        if 0x20 not in records:
            raise ValidationError("Inter source is missing SPACE")
        records[0x202F] = struct.pack("<I", 0x202F) + records[0x20][4:]
    result = []
    for kind, data in blocks:
        if kind == 3:
            data = page_names
        elif kind == 4:
            data = b"".join(records[key] for key in sorted(records))
        result.append((kind, data))
    output = serialise_bmfont(result)
    parse_bmfont(output)
    return output


def font_summary(data: bytes) -> dict:
    blocks = parse_bmfont(data)
    info, common = dict(blocks)[1], dict(blocks)[2]
    return {"face": info[14:-1].decode("utf-8"), "font_size": struct.unpack_from("<h", info)[0],
            "line_height": struct.unpack_from("<H", common)[0], "baseline": struct.unpack_from("<H", common, 2)[0],
            "pages": struct.unpack_from("<H", common, 8)[0], "glyph_count": len(characters(blocks))}


def make_outputs(checkout: Path, lock: dict) -> tuple[dict[str, bytes], dict]:
    project = resource_project(checkout)
    pins = project_pins(lock)
    outputs, records = {}, []
    ofl_path = "Fonts/Inter/OFL.txt"
    ofl = (project / ofl_path).read_bytes()
    verify_bytes(ofl_path, ofl, pins[ofl_path])
    for family in RESTRICTED:
        outputs[f"Fonts/{family}/LICENCE"] = ofl
    for family, weight, source_weight, extension in MAPPINGS:
        source_name = f"Fonts/Inter/Inter-{source_weight}.bin"
        source = (project / source_name).read_bytes()
        verify_bytes(source_name, source, pins[source_name])
        stem = f"{family}-{weight}"
        target_name = f"Fonts/{family}/{stem}{extension}"
        replacement = make_compatible(source, stem, family == "Venera")
        outputs[target_name] = replacement
        count = font_summary(source)["pages"]
        page_records = []
        for page in range(count):
            suffix = f"_{page:0{len(str(count - 1))}d}.png"
            source_page = f"Fonts/Inter/Inter-{source_weight}{suffix}"
            target_page = f"Fonts/{family}/{stem}{suffix}"
            data = (project / source_page).read_bytes()
            verify_bytes(source_page, data, pins[source_page])
            outputs[target_page] = data
            page_records.append({"source": source_page, "output": target_page, "sha256": sha256(data),
                                 "source_git_blob_sha1": pins[source_page]["git_blob_sha1"]})
        records.append({"source": source_name, "output": target_name,
                        "source_git_blob_sha1": pins[source_name]["git_blob_sha1"],
                        "source_sha256": sha256(source), "output_sha256": sha256(replacement),
                        "added_codepoints": ["U+202F"] if family == "Venera" and 0x202F not in characters(parse_bmfont(source)) else [],
                        "metrics": font_summary(replacement), "pages": page_records})
    manifest = {"schema_version": 1, "source_repository": lock["repository"], "source_commit": lock["commit"],
                "pinned_resource_lock_sha256": LOCK_SHA256, "replacement_font": "Inter", "font_license": "OFL-1.1",
                "transformation": "inter-compatibility-v1", "mappings": records,
                "compatibility_only_names": list(RESTRICTED),
                "notes": ["Resource keys remain legacy-compatible; all replacement glyph pixels and metrics derive from Inter.",
                          "Venera-Black uses Inter-Bold; Torus-Alternate uses the corresponding Inter face.",
                          "U+202F is cloned from the replacement Inter SPACE, matching upstream Venera's preprocessing strategy.",
                          "Original Venera .bmfc/.py files are preserved only as historical upstream resource keys; they are not used to generate replacements.",
                          "Remaining non-font resources retain their upstream licences and branding restrictions."]}
    outputs[NOTICE_PATH] = (
        "Open-licensed font substitutions for the danser optional osu!lazer rules host\n\n"
        f"Upstream source: {lock['repository']}/tree/{lock['commit']}\n"
        "Torus, Torus-Alternate and Venera resource names are compatibility keys only.\n"
        "Their former proprietary glyph descriptors and atlases have been removed.\n"
        "Replacement glyph pixels, metrics and kerning come from the pinned Inter bitmap fonts.\n"
        "Matching Inter Light/Regular/SemiBold/Bold weights are used. Venera-Black uses Inter-Bold.\n"
        "Torus-Alternate uses the corresponding ordinary Inter face.\n"
        "U+202F NARROW NO-BREAK SPACE in Venera aliases duplicates Inter's SPACE glyph.\n"
        "The true embedded font face metadata continues to identify Inter.\n"
        "Inter font-size and line-height remain 100; width and baseline metrics differ from the original fonts.\n"
        "This is not a pixel-identical visual replacement. Replay/live runtime validation is still required.\n"
        "Font licence: SIL Open Font License 1.1; see Inter/OFL.txt and each alias directory's LICENCE.\n"
        "Copyright (c) 2016-2019 The Inter Project Authors (me@rsms.me).\n"
        "Alias font payloads and modifications remain under OFL-1.1.\n"
        "Original Venera .bmfc/.py resource files are historical metadata, not this generator's inputs.\n"
        "Other osu! resources keep their upstream licences, including CC-BY-NC 4.0 where applicable;\n"
        "this substitution does not grant rights to osu!/ppy branding or make the entire resource assembly OFL.\n"
        "See OPEN_FONT_PROVENANCE.json for exact source/output hashes and mapping.\n"
    ).encode("utf-8")
    outputs[MANIFEST_PATH] = canonical_json(manifest)
    return outputs, manifest


def forbidden_hashes(lock: dict) -> dict[str, str]:
    return {entry["git_blob_sha1"]: path for path, entry in project_pins(lock).items() if payload_path(path)}


def scan_forbidden(directory: Path, lock: dict) -> list[dict]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValidationError("Scan target must be a real directory")
    forbidden = forbidden_hashes(lock)
    sizes = {entry["size"] for path, entry in project_pins(lock).items() if payload_path(path)}
    matches = []
    for name, path in files_under(directory).items():
        if path.stat().st_size in sizes:
            digest = git_blob_sha1(path.read_bytes())
            if digest in forbidden:
                matches.append({"path": name, "original": forbidden[digest], "git_blob_sha1": digest})
    return matches


def audit(checkout: Path, lock: dict) -> dict:
    project = resource_project(checkout)
    found = files_under(project)
    outputs, manifest = make_outputs(checkout, lock)
    expected = project_pins(lock)
    expected_names = set(expected) | set(outputs)
    if set(found) != expected_names:
        raise ValidationError("Replacement inventory mismatch: " + json.dumps({
            "missing": sorted(expected_names - set(found)), "extra": sorted(set(found) - expected_names)}))
    for name, path in found.items():
        data = path.read_bytes()
        if name in outputs:
            if data != outputs[name]:
                raise ValidationError(f"Replacement/provenance bytes mismatch: {name}")
        else:
            verify_bytes(name, data, expected[name])
    matches = scan_forbidden(project, lock)
    if matches:
        raise ValidationError("Original restricted payloads remain: " + json.dumps(matches))
    return {"status": "passed", "source_commit": lock["commit"], "font_aliases": len(MAPPINGS),
            "replacement_pngs": sum(name.endswith(".png") for name in outputs),
            "verified_resource_files": len(found), "restricted_original_payloads": 0,
            "runtime_validation": "not performed by this generator"}


def preflight(checkout: Path, lock: dict) -> dict:
    verify_pristine(checkout, lock)
    outputs, manifest = make_outputs(checkout, lock)
    project = resource_project(checkout)
    coverage = []
    for record in manifest["mappings"]:
        target = record["output"]
        old = characters(parse_bmfont((project / target).read_bytes()))
        new = characters(parse_bmfont(outputs[target]))
        missing = set(old) - set(new)
        if missing:
            raise ValidationError(f"Replacement glyph coverage is incomplete for {target}: {sorted(missing)}")
        coverage.append({"target": target, "original_glyphs": len(old), "replacement_glyphs": len(new), "missing": []})
    return {"status": "passed", "source_commit": lock["commit"], "pinned_files": len(lock["files"]),
            "font_aliases": len(MAPPINGS), "coverage": coverage}


def apply(checkout: Path, lock: dict) -> dict:
    # Read and validate every original before modifying anything.
    preflight(checkout, lock)
    project = resource_project(checkout)
    outputs, _ = make_outputs(checkout, lock)
    with tempfile.TemporaryDirectory(prefix=".inter-compat-", dir=checkout) as temp:
        temp = Path(temp)
        staged, backup = temp / "staged", temp / "backup"
        staged.mkdir()
        backup.mkdir()
        for family in RESTRICTED:
            shutil.copytree(project / "Fonts" / family, staged / family)
        for name, data in outputs.items():
            if name in (NOTICE_PATH, MANIFEST_PATH):
                continue
            relative = Path(name).relative_to("Fonts")
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        moved = []
        try:
            for family in RESTRICTED:
                destination = project / "Fonts" / family
                destination.rename(backup / family)
                moved.append(family)
                (staged / family).rename(destination)
            for name in (NOTICE_PATH, MANIFEST_PATH):
                (project / name).write_bytes(outputs[name])
            result = audit(checkout, lock)
        except BaseException:
            for family in reversed(moved):
                destination = project / "Fonts" / family
                if destination.exists():
                    shutil.rmtree(destination)
                (backup / family).rename(destination)
            for name in (NOTICE_PATH, MANIFEST_PATH):
                (project / name).unlink(missing_ok=True)
            raise
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("preflight", "apply", "audit", "scan"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        lock = load_lock()
        if args.command == "scan":
            matches = scan_forbidden(args.directory, lock)
            result = {"status": "failed" if matches else "passed", "restricted_original_payloads": matches,
                      "scope": "whole-file payload hashes; extract assembly resources before scanning a DLL"}
            print(json.dumps(result, indent=2))
            return 1 if matches else 0
        result = {"preflight": preflight, "apply": apply, "audit": audit}[args.command](args.directory, lock)
        print(json.dumps(result, indent=2))
        return 0
    except (ValidationError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
