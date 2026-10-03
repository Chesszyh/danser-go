# Pinned Inter compatibility font generator

This kit replaces proprietary Torus, Torus-Alternate and Venera **font data**, not
just their names. It copies genuine, pinned OFL-licensed Inter PNG glyph atlases and
BMFont descriptors, retaining the legacy resource names required by osu!lazer.
It does not change the host, the resource project, assembly metadata or public API.

## Production files

Keep these together:

- `replace_restricted_fonts.py`: Python 3.10+ standard-library CLI
- `pinned-resource-lock.json.gz`: authenticated source lock for all 7,743 resource
  project files plus upstream root README and licence, from osu-resources commit
  `742ca60d4e7273dce0cac2fced7cd132f26f11c8`

The generator authenticates its lock with hardcoded SHA-256
`1ca193dfe0510c2c88ee3d6732b0c187447dc6233262df9b97fd85fb8c08423f`.
It then verifies each source file's byte length and Git blob SHA-1. It accepts a
clean source archive as well as a Git checkout; `.git` is not needed or read.
Unlisted files in the resource project fail verification. Run source audit before
building, because `bin/` and `obj/` are not source files in the lock.

## Commands

```sh
python replace_restricted_fonts.py preflight /path/to/pristine/osu-resources
python replace_restricted_fonts.py apply /path/to/pristine/osu-resources
python replace_restricted_fonts.py audit /path/to/modified/osu-resources
python replace_restricted_fonts.py scan /path/to/extracted-or-staged/resources
python -m unittest -v test_replace_restricted_fonts.py
```

`preflight` is read-only. `apply` changes the explicitly supplied checkout only
after every pinned hash and all original glyph coverage have passed. It verifies
the result and rolls back the changed directories if final verification fails.
An interrupted process or machine failure is not a durable transaction: use a
disposable source checkout and do not package any `.inter-compat-*` temporary
directory after such a failure. Normal success and handled errors remove it.

`apply` is deliberately not idempotent: the second application fails because the
source is no longer pristine. Use `audit` for repeat checking. `audit` verifies
the exact derived bytes, inventories, source Inter hashes, all unchanged resources
and public API source files, and absence of original restricted payloads.

`scan` checks whole-file hashes recursively, including renamed original payloads.
It does **not** search inside a DLL, ZIP or other container. Extract all assembly
manifest resources to an isolated directory first, then scan them. Also compare
the embedded replacements with the manifest's output hashes. A plain scan of a
DLL file is not proof that its embedded fonts were replaced.

## Transformations

- Torus and Torus-Alternate Light/Regular/SemiBold/Bold use matching Inter faces
- Venera-Light uses Inter-Light; Venera-Bold and Venera-Black use Inter-Bold
- Each alias receives all source pages, giving 11 descriptors and 39 PNG pages
- Original binary `.fnt` extensions for Torus-Alternate are retained
- Embedded face metadata continues to identify Inter; page-name blocks are
  rewritten to the exact compatibility filenames
- Each Venera alias adds U+202F by copying Inter's U+0020 blank glyph record;
  other glyph records, Inter metrics and kerning are retained
- The exact pinned OFL/copyright text replaces all three old font licence files
- Historical Venera `.bmfc`/`.py` keys are retained unchanged for full resource-key
  preservation; they are not used to generate the replacement
- Every original resource path remains present; 28 additional PNG pages and two
  new notice/provenance files are added

The exact pinned Inter licence has **no Reserved Font Name declaration**. The
copyright is 2016-2019 The Inter Project Authors. The OFL's general RFN definition
does not itself reserve a name. Keeping Inter's true face metadata is intentional.

## Output notices and manifest

Generated into `osu.Game.Resources/Fonts/`:

- `OPEN_FONT_SUBSTITUTIONS.txt`
- `OPEN_FONT_PROVENANCE.json`

Manifest schema 1 includes source repository/commit, lock hash, replacement font,
licence, transformation identifier and mappings. Each mapping records source and
output paths, original source Git blob SHA-1, source/output SHA-256, added
codepoints, font metrics and each PNG page's source/output paths and hashes.
The manifest is generated during the build from the real pinned inputs; the kit
contains no original proprietary glyph payloads.

## Packaging and validation still required

Stage only the modified resource source tree and required root licence/README,
plus this reproducible generator and lock if distributing build sources. Do not
include `.git`, pristine backups, temporary directories, old resource NuGet
packages, or an unmodified resource DLL. Preserve CC-BY-NC 4.0 and all other
applicable upstream notices: this font substitution does not relicense the whole
resource assembly or grant osu!/ppy trademark rights.

The build owner must preserve the original assembly identity/version and replace
the dependency at restore/reference time. After publish, extract and verify the
actual shipped assembly resources. Run replay and live-mode host tests with that
DLL, including font loading, numeric/score text, relevant whitespace and UI layout.

All fonts retain nominal size/lineHeight 100, but baselines differ (Torus 84,
Venera 75, Inter 80), as do glyph widths. Venera Black/Bold and Torus/Alternate
stylistic distinctions are intentionally reduced. This is not pixel-identical UI.

## Verified in this kit

- 18 synthetic offline unit tests, including format errors, coverage, page count,
  exact blank-space cloning, path validation, source/API changes, symlinks,
  rollback, missing pages and detection of renamed restricted originals
- Read-only real source preflight: all 7,745 pinned files and all 11 glyph sets
- Real apply/audit on a disposable private copy: 7,773 final resource files,
  11 aliases, 39 PNG pages, zero original restricted payloads
- Repeat derivation produced identical bytes; repeated audit passed
- Original restored checkout was reverified pristine afterward
- No assembly build or runtime test was performed by this kit

The native workflow records the current build audit and smoke-test results.
