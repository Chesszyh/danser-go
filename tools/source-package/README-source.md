# danser macOS source and rebuild instructions

This source archive accompanies the same release's app ZIP. Its source-manifest.json
records exact Git commits/trees, materialized osu submodules, linked Go modules and
replacements, native pins, upstream archive hashes, actual NuGet/runtime packages,
and every included file's SHA256. The manifest excludes itself from its file list
and the external checksum covers the complete archive. Notices preserve original
pre-signing binary hashes; macOS signing can subsequently alter Mach-O bytes.

This is source/provenance delivery, not a claim of bit-identical reconstruction or
complete redistribution rights clearance. Original licences remain applicable;
the release's free non-commercial scope does not restrict rights granted by them.

## Contents

- application/: every tracked file from the recorded app commit, with recursively
  materialized submodules. No Git history/credentials or untracked worktree files
- go-modules/: complete directories for actual linked modules only, including
  versioned replacements and any embedded native sources
- go-module-metadata/: available .mod/.info/.ziphash records for those modules;
  older projects can have a Go-generated .mod without an in-tree go.mod
- native/libyuv/: exact pinned tracked source; native/SDL3-3.4.16/: source verified
  against both the pinned archive and the source tree used by the build
- upstream/: when the rules host is included, FFmpeg 4.3.3, OpenTabletDriver and
  TagLibSharp source archives, exact historical FFmpeg scripts and source notices
- notices/: the actual build's collected notices and binary/package evidence

One OpenTabletDriver archive covers all four recorded 0.6.7 packages. TagLibSharp's
upstream archive omits its test-only raw-samples submodule, which is not needed to
compile its library project. See accompanying verification provenance for the
scope of retained prior DLL/PDB checks versus any checks rerun for this release.

## Rebuild application

Use Apple Silicon macOS15+, Xcode command-line tools, the recorded Go toolchain,
and the .NET SDK selected by application/third_party/osu/global.json. Exact .NET
runtime pack identity is in the NuGet inventory. Install CMake, Ninja and FFmpeg CLI
as described in application/docs/macos-port.md and the included workflow. The CLI
is external recording tooling, distinct from the optional host's FFmpeg libraries.

The original scripts query Git for version stamping. Attach the recorded upstream
Git objects to these provided sources without altering their working files:

    cd application
    git init
    git remote add origin https://github.com/Chesszyh/danser-go.git
    git fetch --depth=1 origin APP_COMMIT_FROM_MANIFEST
    git reset --mixed FETCH_HEAD
    git -C third_party/osu init
    git -C third_party/osu remote add origin https://github.com/ppy/osu.git
    git -C third_party/osu fetch --depth=1 origin OSU_COMMIT_FROM_MANIFEST
    git -C third_party/osu reset --mixed FETCH_HEAD

Substitute the exact commits. Check both working-tree diffs. Network access is
also required for SDK installation and NuGet/Go restore; this is not an offline
SDK/package-cache distribution. Then use the release's recorded preparation and
resource-replacement steps before the normal build/test commands:

    ./tools/macos-deps.sh
    ./tools/macos-test.sh
    ./dist-macos.sh SOURCE_REBUILD 0.0.0
    python3 tools/macos-bundle-smoke.py

The build automatically runs application/tools/lazer-fonts/build-resources.sh:
it fetches the exact pinned resource commit, verifies and replaces font data with
Inter, rebuilds the resource package, and restores the host through an isolated
NuGet package source mapping. The supplied modified-resources/ directory contains
the resulting source, generator and provenance for independent inspection.
Do not substitute the unmodified upstream font payload. The same generated
assembly is checked before packaging and after app relocation.

To modify a Go dependency, use an editable app copy and
`go mod edit -replace=ORIGINAL_MODULE_PATH=/absolute/supplied/module-directory`.
Use each manifest entry's original.path and directory. If the supplied old module
lacks go.mod, copy its metadata .mod to go.mod in an editable dependency copy.
Keep the original cgo flags/build tags from dist-macos.sh and tools/macos-go.sh.

For modified libyuv/SDL, build supplied native sources out of tree with the CMake
options from application/tools/macos-deps.sh. Set DANSER_MACOS_DEPS_DIR to a separate
dependency root containing the rebuilt libyuv.a/libSDL3.dylib and other required
native libraries/notices. Running dependency preparation on modifications would
deliberately restore its pinned sources, so build modified trees separately.

## Rebuild/replace separately distributed LGPL libraries

Applicable when optionalRulesHostIncluded is true. Exact source/binary mappings
are in upstream/ffmpeg-notices/SOURCES.json and upstream/lgpl-sources/SOURCES.json.

FFmpeg: on macOS with Xcode tools, make, xz and NASM as required by configure:

    sh ./build-ffmpeg-from-bundled-source.sh /absolute/new/build-directory

The wrapper uses the verified bundled tar stream, unchanged historical flags,
arm64/x86_64 builds and lipo to make universal libraries. Inspect configure output
for modern SDK compatibility; bit-identical results are not promised.

TagLibSharp: unpack the archive, read its README, and run from its root:

    dotnet build src/TaglibSharp/TaglibSharp.csproj -c Release -f netstandard2.0

OpenTabletDriver: unpack its archive, read its README/Directory.Build.props, and run:

    dotnet build OpenTabletDriver/OpenTabletDriver.csproj -c Release -f net8.0

Its referenced Plugin/Native/Configurations projects are built too. SDKs and
NuGet restore are required. These commands are derived from project files; the
source packager does not execute or validate these rebuilds.

Put compatible rebuilt DLLs/dylibs in a private copy of
`danser.app/Contents/MacOS/lazer-rules-host/`, preserving filenames. Replacements
invalidate the ad-hoc signature; re-sign your local app with
`codesign --force --deep --sign - /path/to/danser.app` and retest. Preserve notices.
No additional restriction on permitted LGPL modification/debugging is imposed.

BASS/BASSmix/BASS_FX remain proprietary vendor components. Their source is not
supplied; preserve vendor notices. SoundTouch references inside BASS_FX notices do
not establish that a verified vendor-internal source payload is supplied here.
