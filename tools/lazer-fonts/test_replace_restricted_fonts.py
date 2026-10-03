import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import replace_restricted_fonts as r


def fixture_font(face="Inter", pages=2, codes=(32, 65), baseline=80):
    info = struct.pack("<hBBHBBBBBBBB", 100, 0x40, 0, 100, 4, 0, 0, 0, 0, 4, 4, 0) + face.encode() + b"\0"
    common = struct.pack("<HHHHHBBBBB", 100, baseline, 1024, 1024, pages, 0, 0, 4, 4, 4)
    names = b"".join(f"{face}_{page:0{len(str(pages - 1))}d}.png".encode() + b"\0" for page in range(pages))
    chars = b"".join(struct.pack("<IHHHHhhhBB", code, 0, 0, 1 if code == 32 else 7,
                                  1 if code == 32 else 10, 0, 5, 6, 0, 15) for code in codes)
    return r.serialise_bmfont([(1, info), (2, common), (3, names), (4, chars), (5, b"")])


def create_checkout(root):
    project = root / r.PROJECT
    data = {"README.md": b"synthetic fixture root", "LICENCE.md": b"fixture licence",
            f"{r.PROJECT}/ResourceAssembly.cs": b"public API fixture",
            f"{r.PROJECT}/osu.Game.Resources.csproj": b"unchanged project",
            f"{r.PROJECT}/Textures/example.png": b"unchanged other resource",
            f"{r.PROJECT}/Fonts/Inter/OFL.txt": b"test-only OFL placeholder"}
    for weight in ("Light", "Regular", "SemiBold", "Bold"):
        data[f"{r.PROJECT}/Fonts/Inter/Inter-{weight}.bin"] = fixture_font(face="Inter " + weight)
        for page in range(2):
            data[f"{r.PROJECT}/Fonts/Inter/Inter-{weight}_{page}.png"] = f"synthetic open PNG {weight} {page}".encode()
    for family in r.RESTRICTED:
        data[f"{r.PROJECT}/Fonts/{family}/LICENCE"] = b"original restricted licence " + family.encode()
    for family, weight, source_weight, extension in r.MAPPINGS:
        codes = (32, 65, 8239) if family == "Venera" else (32, 65)
        stem = f"{family}-{weight}"
        data[f"{r.PROJECT}/Fonts/{family}/{stem}{extension}"] = fixture_font(face=stem, pages=1, codes=codes)
        data[f"{r.PROJECT}/Fonts/{family}/{stem}_0.png"] = b"synthetic restricted PNG " + stem.encode()
    data[f"{r.PROJECT}/Fonts/Venera/Venera-settings.bmfc"] = b"historical config"
    data[f"{r.PROJECT}/Fonts/Venera/venera-postprocess.py"] = b"historical script"
    for name, content in data.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    lock = {"repository": "https://github.com/ppy/osu-resources", "commit": r.COMMIT,
            "files": {name: {"size": len(content), "git_blob_sha1": r.git_blob_sha1(content)} for name, content in data.items()}}
    return lock


class BitmapTests(unittest.TestCase):
    def test_binary_roundtrip(self):
        data = fixture_font()
        self.assertEqual(r.serialise_bmfont(r.parse_bmfont(data)), data)

    def test_page_names_and_face(self):
        old = fixture_font(pages=12)
        output = r.make_compatible(old, "Torus-Regular", False)
        blocks = dict(r.parse_bmfont(output))
        self.assertEqual(blocks[1], dict(r.parse_bmfont(old))[1])
        self.assertIn(b"Torus-Regular_00.png\0", blocks[3])
        self.assertTrue(blocks[3].endswith(b"Torus-Regular_11.png\0"))

    def test_narrow_space_is_only_added_character(self):
        old = fixture_font()
        output = r.make_compatible(old, "Venera-Bold", True)
        before = r.characters(r.parse_bmfont(old))
        after = r.characters(r.parse_bmfont(output))
        self.assertEqual(set(after) - set(before), {8239})
        self.assertEqual(after[8239][4:], before[32][4:])
        for key in before:
            self.assertEqual(after[key], before[key])

    def test_existing_narrow_space_is_preserved(self):
        old = fixture_font(codes=(32, 65, 8239))
        new = r.make_compatible(old, "Venera-Bold", True)
        self.assertEqual(r.characters(r.parse_bmfont(new)), r.characters(r.parse_bmfont(old)))

    def test_missing_space_rejected(self):
        with self.assertRaises(r.ValidationError):
            r.make_compatible(fixture_font(codes=(65,)), "Venera-Bold", True)

    def test_path_injection_rejected(self):
        with self.assertRaises(r.ValidationError):
            r.make_compatible(fixture_font(), "../oops", True)

    def test_corrupt_formats_rejected(self):
        valid = fixture_font()
        cases = [b"", b"BMF\x02" + valid[4:], valid[:-1], valid + b"x",
                 valid + struct.pack("<BI", 1, 0), valid[:5] + struct.pack("<I", 9999999) + valid[9:]]
        for bad in cases:
            with self.subTest(size=len(bad)), self.assertRaises(r.ValidationError):
                r.parse_bmfont(bad)

    def test_page_count_and_duplicate_glyph_rejected(self):
        blocks = r.parse_bmfont(fixture_font())
        corrupt = [(kind, b"only-one.png\0" if kind == 3 else data) for kind, data in blocks]
        with self.assertRaises(r.ValidationError):
            r.parse_bmfont(r.serialise_bmfont(corrupt))
        corrupt = [(kind, data + data[:20] if kind == 4 else data) for kind, data in blocks]
        with self.assertRaises(r.ValidationError):
            r.parse_bmfont(r.serialise_bmfont(corrupt))


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lock = create_checkout(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_apply_preserves_paths_api_and_deterministic_outputs(self):
        before = r.files_under(self.root / r.PROJECT)
        source_api = (self.root / r.PROJECT / "ResourceAssembly.cs").read_bytes()
        expected, manifest = r.make_outputs(self.root, self.lock)
        self.assertEqual(expected, r.make_outputs(self.root, self.lock)[0])
        self.assertEqual(r.preflight(self.root, self.lock)["font_aliases"], 11)
        result = r.apply(self.root, self.lock)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(set(before).issubset(r.files_under(self.root / r.PROJECT)))
        self.assertEqual(source_api, (self.root / r.PROJECT / "ResourceAssembly.cs").read_bytes())
        self.assertEqual(r.audit(self.root, self.lock)["restricted_original_payloads"], 0)
        for name, data in expected.items():
            self.assertEqual((self.root / r.PROJECT / name).read_bytes(), data)
        # Re-applying to a modified checkout is explicitly rejected; audit is its safe repeat operation.
        with self.assertRaises(r.ValidationError):
            r.apply(self.root, self.lock)

    def test_wrong_source_hash_leaves_checkout_untouched(self):
        path = self.root / r.PROJECT / "Fonts/Inter/Inter-Light.bin"
        path.write_bytes(path.read_bytes() + b"corrupt")
        before = {name: p.read_bytes() for name, p in r.files_under(self.root / r.PROJECT).items()}
        with self.assertRaises(r.ValidationError):
            r.apply(self.root, self.lock)
        self.assertEqual(before, {name: p.read_bytes() for name, p in r.files_under(self.root / r.PROJECT).items()})

    def test_original_renamed_payload_detected(self):
        data = (self.root / r.PROJECT / "Fonts/Torus/Torus-Light_0.png").read_bytes()
        r.apply(self.root, self.lock)
        destination = self.root / r.PROJECT / "Textures/deep/subfolder/renamed.dat"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(data)
        self.assertEqual(len(r.scan_forbidden(self.root / r.PROJECT, self.lock)), 1)
        with self.assertRaises(r.ValidationError):
            r.audit(self.root, self.lock)

    def test_mutated_alias_and_manifest_rejected(self):
        r.apply(self.root, self.lock)
        path = self.root / r.PROJECT / "Fonts/Venera/Venera-Black.bin"
        path.write_bytes(path.read_bytes() + b"corrupt")
        with self.assertRaises(r.ValidationError):
            r.audit(self.root, self.lock)

    def test_missing_page_and_extra_files_rejected(self):
        r.apply(self.root, self.lock)
        (self.root / r.PROJECT / "Fonts/Torus/Torus-Light_1.png").unlink()
        with self.assertRaises(r.ValidationError):
            r.audit(self.root, self.lock)

    def test_mutated_public_api_rejected(self):
        r.apply(self.root, self.lock)
        (self.root / r.PROJECT / "ResourceAssembly.cs").write_text("changed")
        with self.assertRaises(r.ValidationError):
            r.audit(self.root, self.lock)

    def test_failure_rolls_back_exactly(self):
        before = {name: p.read_bytes() for name, p in r.files_under(self.root / r.PROJECT).items()}
        with patch.object(r, "audit", side_effect=r.ValidationError("injected verification failure")):
            with self.assertRaises(r.ValidationError):
                r.apply(self.root, self.lock)
        self.assertEqual(before, {name: p.read_bytes() for name, p in r.files_under(self.root / r.PROJECT).items()})

    def test_symlink_rejected(self):
        (self.root / r.PROJECT / "symlink").symlink_to(self.root / "README.md")
        with self.assertRaises(r.ValidationError):
            r.preflight(self.root, self.lock)

    def test_full_glyph_coverage_checked(self):
        target = self.root / r.PROJECT / "Fonts/Torus/Torus-Regular.bin"
        target.write_bytes(fixture_font(face="Torus", pages=1, codes=(32, 65, 9999)))
        data = target.read_bytes()
        self.lock["files"][r.PROJECT + "/Fonts/Torus/Torus-Regular.bin"] = {"size": len(data), "git_blob_sha1": r.git_blob_sha1(data)}
        with self.assertRaises(r.ValidationError):
            r.preflight(self.root, self.lock)

    def test_pinned_lock_authentication(self):
        self.assertEqual(r.load_lock()["commit"], r.COMMIT)
        path = self.root / "bad-lock.json"
        path.write_text("{}")
        with self.assertRaises(r.ValidationError):
            r.load_lock(path)


if __name__ == "__main__":
    unittest.main()
