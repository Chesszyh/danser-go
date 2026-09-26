# macOS port status

This document is the authoritative checklist and evidence log for the Apple
Silicon macOS port. `VERIFIED` means the stated behavior was exercised on the
current Mac. Every acceptance row must be either verified or evidence-backed
`BLOCKED`; a blocked item identifies the unavailable proof and why this host
cannot supply it.

## Baseline

- Branch: `codex/macos-port`
- Upstream: `origin/dev` at `3eb75a34babb48590954deb836a585fe8174a1d5`
- Host: Apple M4 Mac mini, macOS 26.6.2, arm64
- Toolchain: Go 1.26.1 downloaded by `GOTOOLCHAIN=auto`; Apple clang 21
- Target: Apple Silicon macOS, including MacBook Air. Thermal behavior and
  model-specific display behavior still require a final MacBook Air check.

## Acceptance checklist

| Area | Status | Evidence or next proof |
| --- | --- | --- |
| Isolated Git worktree and progress log | VERIFIED | This branch/worktree is based on the fetched `origin/dev`; the original `master` checkout remains untouched. |
| Darwin/arm64 build | VERIFIED | `go test ./...` and `go build ./...` pass, and the root binary is an arm64 Mach-O. Go 1.26 printf-vet findings were fixed in a separate commit. |
| SDL3 window and OpenGL 4.1 Core context | VERIFIED | Native Cocoa window created with source-built SDL 3.4.16; runtime logged Apple M4, OpenGL 4.1 Metal 90.5, GLSL 4.10, and the selected compatibility capabilities. |
| BASS audio and libyuv integration | VERIFIED | The default BASS device initializes at 17 ms; a real recording completed its libyuv conversion and contains non-silent AAC audio (`mean_volume=-37.2 dB`, `max_volume=-13.3 dB`). |
| OpenGL 4.1 buffer/VAO/draw path | VERIFIED | Native pixel-readback regression verifies visible straight and bent slider tracks. A 4,687-frame replay also ran with `UsePersistentBuffers=true` while the capability report showed buffer storage unavailable, selecting the streaming fallback. |
| OpenGL 4.1 texture/framebuffer path | VERIFIED | Screenshot and recording exercised readback and framebuffer effects. The focused OpenGL diagnostic passed texture-layer preservation/clear/readback and 4x MSAA resolve without a GL error. |
| Launcher, input, scaling, and fullscreen | VERIFIED | The launcher ran from the app bundle; synthetic SDL key-down/up events updated both state and listeners; windowed logical coordinates and a 1920x1080 fullscreen drawable were exercised. |
| Launcher playback and settings round trip | VERIFIED | The 2026-09-12 native regression exercised the actual danse button handler, window minimization, playback, Ctrl+O settings restoration, and Escape returning to the launcher. See the dated evidence below. |
| Beatmap watch/replay for at least 60 seconds | VERIFIED | The fixed 75-second smoke map rendered continuously for over 95 wall-clock seconds. Its generated replay parsed all 4,687 frames, ran to the score screen, and reported a 74,992 ms replay duration. |
| Screenshot | VERIFIED | `screenshots/macos-smoke-40s.png` is a visually inspected 1280x720 frame with background, storyboard sprite, hit circle, and cursor. |
| Recording | VERIFIED | `videos/macos-smoke-video.mp4` decodes as 640x360 H.264 at 30 fps plus 48 kHz stereo AAC; duration is 17.0 seconds. An extracted frame was visually inspected. |
| Retina/high-DPI | VERIFIED (render targets); physical display transitions unverified | Native regression tests cover 1x/2x/1x Bloom and cursor composition, 2x merged sliders, and storyboard clipping in target pixels. These offscreen checks do not verify moving a visible window between physical displays. |
| `.app` bundle | VERIFIED | The ad-hoc-signed arm64 bundle has a valid icon/plist, one `@executable_path/../Frameworks` rpath, and a self-contained official osu!lazer rules host. The executable reports `minos 15.0`, the bundled SDL reports `minos 11.0`, and the plist declares macOS 15. `open -n` reached launcher/OpenGL/BASS/FFmpeg using packed assets and `~/Library/Application Support/danser`. |
| Windows/Linux preservation | VERIFIED | Platform-specific context creation remains behind build tags and graphics selection is capability-based. Native tests pass; the pure `env` and `glcaps` test binaries cross-compile for amd64 Linux and Windows. Runtime testing on those operating systems was not performed. |
| Final source/documentation/commit audit | VERIFIED | Shell syntax, formatting, `git diff --check`, `go test ./...`, `go build ./...`, generated artifacts, build tags, and the scoped diff were checked before the final commit. |

## Known OpenGL compatibility work

The upstream extension gate requires ARB clear-texture, direct-state-access,
texture-storage, vertex-attrib-binding, and buffer-storage. The code also calls
post-4.1 functions outside that gate, notably base-instance draws,
`CopyImageSubData`, and recording-time `GetTextureSubImage`. The port must
select behavior by capability inside the existing graphics modules rather than
scatter OS checks through rendering callers.

## Build and run on Apple Silicon

Install Go, the .NET SDK selected by `third_party/osu/global.json`, and the
Homebrew build/runtime dependencies. Then stage the proprietary BASS binaries
from their official downloads and build the local app bundle:

```sh
brew install ffmpeg cmake ninja
./tools/macos-deps.sh
./dist-macos.sh 0.0.0-macos-dev 0.0.0
open dist/build-macos/danser.app
```

The generated arm64 application targets macOS 15 or newer. It includes the
self-contained `lazer-rules-host/danser-lazer-rules` companion, so official
osu!lazer scoring does not require a system .NET installation. The module's Go
1.26 toolchain itself supports macOS 12 according to
[Go's Darwin support table](https://go.dev/wiki/Darwin), but the pinned cimgui
dependency ships an arm64 static library built for macOS 15; the bundle
declares the higher, truthful minimum instead of relying on a misleading lower
deployment target.

The first argument is danser's displayed version and the second must be a
numeric macOS bundle version. The result is ad-hoc signed for local use, not
Developer ID signed or notarized. Shipping it through Gatekeeper requires an
Apple Developer identity and notarization credentials that are intentionally
outside this port. Settings, databases, screenshots, and videos from the app
bundle live under `~/Library/Application Support/danser`; the bundle itself
contains only executables, packed assets, libraries, licensing files, and its
icon. SDL3, BASS, and the official rules host are bundled; FFmpeg remains a
runtime dependency. It is located next to danser or through `PATH`, then in
`/opt/homebrew/bin` and `/usr/local/bin` on macOS. Finder launches therefore do
not require a shell-configured Homebrew `PATH`. To select a different installation,
set `DANSER_FFMPEG_DIR` to the directory containing both `ffmpeg` and `ffprobe`;
an invalid explicit directory produces an error instead of selecting another copy.

### Custom dependency directories

Use the same `DANSER_MACOS_DEPS_DIR` for preparing dependencies, Go commands, and
packaging. The Go wrapper disables the default cgo search paths and supplies the
selected directory for both linking and runtime loading. Plain `go build` and
`go test` continue to use `.deps/macos`.

```sh
export DANSER_MACOS_DEPS_DIR="$HOME/Library/Caches/danser native deps"
./tools/macos-deps.sh
./tools/macos-go.sh build -o danser .
./tools/macos-test.sh
./dist-macos.sh 0.0.0-macos-dev 0.0.0
```

Use `DANSER_MACOS_GO_TAGS` for additional build tags when using the wrapper.
Packaged executables use only `@executable_path/../Frameworks` as their library
search path; they do not retain a reference to the dependency cache.

### Graphics regression checks

`./tools/macos-test.sh` runs all Go tests with native OpenGL checks enabled,
serializes package execution, and runs the SDL/OpenGL smoke program. The native
checks use hidden windows and isolated assets, without reading user settings or
beatmaps. Ordinary `go test ./...` still skips these checks unless
`DANSER_TEST_OPENGL=1` is set.

The regression suite covers:

- Bloom and additive cursor composition at 1x, 2x, and restored 1x backing sizes.
- Merged sliders at 1x and 2x, and storyboard clipping in target pixel coordinates.
- Texture expansion with scissor testing and color/depth write masks, including
  preservation of caller state and existing texture pixels.
- Legacy vertex attribute offsets with and without native base-instance support.
- FFmpeg lookup with a minimal Finder-style `PATH`, explicit directories, and
  retry after a missing dependency is supplied.

The backing-size tests exercise real GPU rendering into offscreen targets. They
do not replace a physical monitor-switching or long-duration thermal test.
The `macOS compatibility` GitHub Actions workflow runs these checks and builds
the signed app bundle on the `macos-15` arm64 runner for pull requests and pushes
to `master`. Runner architectures are listed in the
[GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

### 2026-09-26 compatibility fixes

Offscreen passes now set and restore their own viewport and scissor dimensions.
Storyboard clipping projects into the active viewport rather than the configured
logical window size. Texture clear/copy fallbacks isolate draw state, and native
base-instance draws no longer also shift legacy attribute pointers. These
regressions fail when tested against the pre-fix graphics implementations.

## Evidence log

### 2026-09-04: repository and host baseline

- Live `origin/dev` resolved to `3eb75a34babb48590954deb836a585fe8174a1d5`.
- The original checkout was `master` with only its user-owned untracked
  `GOAL.md`; the isolated worktree was created at
  `/Users/chesszyh987/Develop/danser-go-macos-port`.
- Go automatically supplied 1.26.1 for the module. Homebrew supplied the build
  tools and FFmpeg 9.0.1. SDL 3.4.16 is built from its checksum-verified official
  source archive with a macOS 11.0 deployment target. Homebrew libyuv and macOS
  BASS libraries were not found in the initial dependency probe.
- Upstream bundles Windows DLLs and x86-64 Linux `.so` files, not Darwin dylibs.

### 2026-09-04: Darwin dependencies and build

- `tools/macos-deps.sh` stages SDL 3.4.16 built from its official source,
  official BASS/BASSmix/BASS FX universal dylibs, and an arm64 static libyuv
  built from pinned upstream revision
  `eb6e7bb63738e29efd82ea3cf2a115238a89fa51`. SDL and libyuv target macOS
  11.0; the final cgo link and bundle target macOS 15.0 to match the pinned
  cimgui arm64 archive. This avoids inheriting the build host's macOS 26
  deployment target or claiming support below the newest bundled object.
- The Darwin cgo link paths resolve all three BASS dylibs and libyuv. `go build
  ./...` and `go build -o danser .` passed; `file danser` reports an arm64
  Mach-O executable.
- `go test -vet=off ./...` initially passed four tests across 97 packages.
  Normal `go test ./...` then exposed Go 1.26 printf-analyzer findings in the
  launcher and scoreboard. Their format strings were corrected without
  changing UI behavior; normal `go test ./...` now passes.

### 2026-09-04: OpenGL 4.1 compatibility probe

- The first native launch originally stopped at the extension gate. After
  capability-based selection, it reports OpenGL 4.1 with DSA, buffer storage,
  vertex-attrib binding, clear texture, base instance, copy image, texture
  subimage readback, and KHR debug output unavailable; ARB texture storage is
  available.
- The compatibility path replaces DSA buffer, VAO, texture, renderbuffer, and
  framebuffer operations with bind-preserving OpenGL 4.1 calls. It substitutes
  a mapped streaming buffer when persistent storage is unavailable and emulates
  base-instance fetch offsets in the VAO.
- A real launcher run passed shader setup, texture-atlas creation, texture
  uploads, framebuffer effect setup, and BASS initialization. It then remained
  live for more than 20 seconds until an intentional `Ctrl-C`; no unsupported
  OpenGL entry point or driver texture warning remained.

### 2026-09-04: fixed-map gameplay, screenshot, and recording

- `tools/macos-smoke-fixture.sh` creates a deterministic 75-second map with a
  PCM audio track, background, animated storyboard sprite, circles, sliders,
  and spinners. `tools/macos-smoke-replay` creates a matching deterministic
  stable-format replay and has a write/parse round-trip test.
- A windowed quickstart run loaded the fixed map, audio, storyboard, skin,
  textures, sliders, and UI, then rendered for over 95 wall-clock seconds until
  an intentional `Ctrl-C`. Frame time was normally 3-5 ms; isolated slow-frame
  messages were 18-25 ms. This is a functional smoke result, not a MacBook Air
  thermal benchmark.
- macOS cannot use SDL's generic `offscreen` video driver with an OpenGL
  context. The recording path now creates a hidden Cocoa/OpenGL window instead.
  The fixed-time screenshot then completed normally. Its SHA-256 is
  `98426404d2e834f5ef93e10d38ea4dd68a243b7f30676d9ee75e3dc353f26496`.
- OpenGL 4.1 recording uses an ordinary pixel-pack buffer plus
  `glGetBufferSubData` when persistent buffer storage is absent, and
  `glGetTexImage` when texture-subimage readback is absent. The generated MP4
  has SHA-256
  `e3173ba0543f2b3152774794a260142714bd860b3ab97ae9fb260afd0b0e44f0`.
  `ffprobe` reports H.264 640x360 at 30 fps, AAC 48 kHz stereo, 17.0 seconds,
  631096 bytes. FFmpeg `volumedetect` reports finite mean and peak levels, so
  the audio stream is not silent.

### 2026-09-04: focused compatibility, replay, and fullscreen checks

- `tools/gl41-smoke` created a hidden Cocoa OpenGL 4.1 context and passed
  texture-layer preservation, zero-clear and readback, 4x multisample resolve,
  and SDL keyboard state/listener checks without an OpenGL error.
- The generated replay contains 4,687 frames over 74,992 ms. It loaded and ran
  to the score screen with `UsePersistentBuffers=true` while the live capability
  report showed buffer storage, DSA, vertex-attrib binding, and base-instance
  unavailable. This exercised the streaming buffer, legacy VAO, and emulated
  base-instance draw path in real gameplay.
- A separate fullscreen run created a 1920x1080 logical and pixel-size drawable,
  initialized OpenGL 4.1 and BASS, loaded the replay/storyboard, and rendered to
  the score screen. Both replay runs were stopped intentionally after their
  interactive result screens remained open.

### 2026-09-04: high DPI and application bundle

- SDL documents that window coordinates and drawable pixel size are distinct,
  and that macOS OpenGL apps require both `SDL_WINDOW_HIGH_PIXEL_DENSITY` and
  `NSHighResolutionCapable=YES`. The port uses logical coordinates for input
  and window bounds, but `SDL_GetWindowSizeInPixels` for the viewport and final
  framebuffer. See the [SDL high-DPI guide](https://wiki.libsdl.org/SDL3/README-highdpi)
  and [SDL_CreateWindow](https://wiki.libsdl.org/SDL3/SDL_CreateWindow).
- `dist-macos.sh` builds an arm64 release bundle, publishes the official rules
  host as a self-contained `osx-arm64` application, packs assets, includes SDL3
  and the three BASS dylibs under `Contents/Frameworks`, rewrites its rpath to
  `@executable_path/../Frameworks`, creates an application icon and
  `Info.plist`, and applies an ad-hoc signature. `codesign --verify --deep
  --strict` passes and `otool` shows no worktree-absolute rpath.
- A launch through `/usr/bin/open -n` reached the launcher, OpenGL 4.1, BASS,
  FFmpeg discovery, and database initialization. The process remained live
  until that single test instance was intentionally stopped. The bundle stores
  mutable data in `~/Library/Application Support/danser`, not inside the signed
  app.
- `system_profiler SPDisplaysDataType` reports only a 1920x1080 display whose UI
  size is also 1920x1080. Bare and bundled windows therefore both report 1.0
  pixel density. The code/configuration is verified at 1x; actual 2x Retina and
  MacBook Air behavior remain external-hardware blockers. Apple also documents
  `NSHighResolutionCapable` as the Cocoa high-resolution opt-in.
- Apple has deprecated OpenGL since macOS 10.14 but retains it for compatibility;
  the chosen compatibility backend is deliberately narrower than a Metal
  rewrite. See Apple's [macOS Mojave release notes](https://developer.apple.com/documentation/macos-release-notes/macos-mojave-10_14-release-notes)
  and [OpenGL profile constants](https://developer.apple.com/documentation/appkit/opengl-profiles).

### 2026-09-12: launcher playback thread regression

- The delayed Watch-mode button handler called `startDanser` from a background
  goroutine. Its window minimization entered Cocoa off the main thread and
  terminated the launcher with `SIGTRAP`. The native crash diagnostic states
  `Must only be used from the main thread`; the application stack runs through
  `drawLowerPanel`, `startDanser`, and `gcontext.Minimize`. SDL documents the
  [main-thread requirement for window minimization](https://wiki.libsdl.org/SDL3/SDL_MinimizeWindow).
- Playback startup now returns to the existing main-thread queue after the
  delay. The player's Ctrl+O request also opens settings, restores the window,
  and focuses it on that queue.
- A temporary Go source overlay selected `INTERNET YAMERO [CRAZY]` and triggered
  the existing danse button handler. It left the subprocess and window code
  intact. The original handler exited with status 2 after 1.35 seconds; the
  corrected handler started the same map and remained alive for the 12-second
  observation period. The launcher reported 800x534 logical / 1600x1068 pixels,
  and playback reported 1920x1080 logical / 3840x2160 pixels.
- The subsequent native lifecycle check verified that the launcher minimized,
  Ctrl+O restored it, Escape ended playback normally, and the launcher remained
  alive and restored. `go test ./...` passed. The launcher has no isolated
  native-window unit-test seam; this regression was checked through the real
  macOS runtime. The diagnostic overlay is excluded from the shipped source
  and app bundle.
- The initial port validation exercised the launcher and direct playback
  separately. It did not cover the launcher's transition into playback.

To repeat the runtime check, open the app, select a standard-mode map, choose
Watch, and click **danse!**. During playback press **Ctrl+O**, then return focus
to playback and press **Escape**. The settings window should open and the
launcher should remain usable after playback exits.

### 2026-09-12: visible slider tracks

- The slider depth framebuffer was complete and cleared successfully, but its
  line, joint, and cap draw calls returned `GL_INVALID_OPERATION` (`0x502`) on
  Apple OpenGL 4.1. Its depth texture stayed at the clear value of 1, so the
  coloring pass discarded the entire track. Hit circles, reverse arrows, and
  gameplay judgment were unaffected.
- The two depth-rendering programs now include `sliderdepth.fsh`. Its empty
  fragment stage preserves rasterized depth and lets the existing coloring pass
  draw the track on macOS.
- `TestSliderTrackRendering` exercises the production slider renderer in a
  hidden native context. It checks OpenGL errors, depth writes, visible pixels
  along straight and bent tracks, and transparency outside the tracks. The
  original programs failed with `0x502`; adding the fragment stage passes the
  test. This checks actual drawing, beyond successful shader compilation and
  program linking.
- Screenshots of `Raise the Huddle [osu!ph Cavalry Battle]` at 1.0 seconds were
  compared using the same copied configuration. The corrected packed-asset
  build shows the previously absent curved track and border. The original
  smoke screenshot at 40 seconds showed a hit circle and did not establish
  slider-track visibility.

Run the native regression from the repository root in a macOS desktop session:

```sh
DANSER_TEST_OPENGL=1 DANSER_MACOS_DEPS_DIR="$PWD/.deps/macos" GOMAXPROCS=2 \
  go test ./app/graphics/sliderrenderer -run TestSliderTrackRendering -count=1 -v
```

Ordinary `go test ./...` skips this native-context test unless explicitly
enabled. The test uses isolated assets and does not load user settings or maps.

### 2026-09-14: bundled official osu!lazer rules host

- The macOS distribution publishes `Danser.LazerRulesHost.csproj` for
  `osx-arm64` as a self-contained application under
  `Contents/MacOS/lazer-rules-host`, which is the path resolved by the bundled
  danser executable. The pinned osu! licence is installed under
  `Contents/Resources`.
- The signed bundle's host runs with `DOTNET_ROOT` set to a nonexistent path,
  confirming that it does not depend on a system .NET runtime. A generated
  4,687-frame replay was rejudged against the smoke beatmap; the host returned
  protocol version 3, the pinned osu! source revision, chronological judgements,
  and actual/full-combo/perfect-play performance values.
- `go test -count=1 ./...`, `go build ./...`, shell syntax validation, and deep
  bundle signature verification passed after the packaging change.

### Resource-safe verification policy

An independent lc0/fastchess experiment was detected while final checks were
being prepared. All danser processes started by this task were stopped, CPU
tests were run with `nice -n 15` and `GOMAXPROCS=2`, and OpenGL runs were
deferred until the experiment naturally completed all 100 games. The
application no longer overrides the Go runtime's `GOMAXPROCS` selection, so an
environment limit is respected during smoke runs while the default remains
unchanged when the variable is unset.

## Reproducible commands

The following are the concise commands used for the final verification. The
commands that exercise the GPU should be run serially, after checking for other
active GPU experiments.

```sh
./tools/macos-deps.sh
GOMAXPROCS=2 nice -n 15 go test ./...
GOMAXPROCS=2 nice -n 15 go build ./...
./tools/macos-smoke-fixture.sh
GOMAXPROCS=2 nice -n 15 go run ./tools/gl41-smoke .deps/macos
GOMAXPROCS=2 nice -n 15 ./dist-macos.sh 0.0.0-macos-dev 0.0.0
codesign --verify --deep --strict --verbose=2 dist/build-macos/danser.app
otool -l dist/build-macos/danser.app/Contents/MacOS/danser
open -n dist/build-macos/danser.app
ffprobe -v error -show_entries format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels -of json videos/macos-smoke-video.mp4
ffmpeg -threads 1 -i videos/macos-smoke-video.mp4 -vn -af volumedetect -f null -
```
