# macOS port status

This document is the authoritative checklist and evidence log for the Apple
Silicon macOS port. `VERIFIED` means the stated behavior was exercised on the
current Mac; `IN_PROGRESS` and `TODO` are not completion states. A `BLOCKED`
item must include a reproduced failure, researched alternatives, and the
attempts that ruled them out.

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
| Darwin/arm64 build | VERIFIED | `go test -vet=off ./...` passed in 97 packages, `go build ./...` passed, and the root binary is an arm64 Mach-O. Normal `go test ./...` is pending upstream vet fixes tracked below. |
| SDL3 window and OpenGL 4.1 Core context | VERIFIED | Native Cocoa window created with Homebrew SDL 3.4.14; runtime logged Apple M4, OpenGL 4.1 Metal 90.5, GLSL 4.10, and the selected compatibility capabilities. |
| BASS audio and libyuv integration | IN_PROGRESS | Universal BASS libraries initialize the default device at 17 ms latency; beatmap playback and recording-time libyuv conversion remain to verify. |
| OpenGL 4.1 buffer/VAO/draw path | IN_PROGRESS | Launcher exercises legacy buffer and VAO creation/upload/draw. Persistent-buffer substitution and nonzero base-instance behavior remain to verify in gameplay. |
| OpenGL 4.1 texture/framebuffer path | IN_PROGRESS | Launcher exercises array texture allocation/upload/clear and basic framebuffer setup. Resize/copy, multisample resolve, and representative framebuffer effects remain to verify. |
| Launcher, input, scaling, and fullscreen | IN_PROGRESS | Launcher remains live without a GL crash after initialization; interaction, resize, fullscreen, and coordinate checks remain. |
| Beatmap watch/replay for at least 60 seconds | TODO | Use a fixed local or redistributable map; verify audio sync, sliders, storyboard, textures, and UI. |
| Screenshot | TODO | Produce and inspect a representative screenshot at a fixed timestamp. |
| Recording | TODO | Produce a short MP4 and verify streams, duration, dimensions, and decode with `ffprobe`. |
| Retina/high-DPI | TODO | Verify logical window coordinates versus drawable pixels and resize events. |
| `.app` bundle | TODO | Launch from Finder/`open`, with dylibs and resources resolved from the bundle. |
| Windows/Linux preservation | TODO | Run applicable tests/build checks and keep modern paths available where required. |
| Final source/documentation/commit audit | TODO | No failed attempts or `TODO`/`IN_PROGRESS` checklist entries remain. |

## Known OpenGL compatibility work

The upstream extension gate requires ARB clear-texture, direct-state-access,
texture-storage, vertex-attrib-binding, and buffer-storage. The code also calls
post-4.1 functions outside that gate, notably base-instance draws,
`CopyImageSubData`, and recording-time `GetTextureSubImage`. The port must
select behavior by capability inside the existing graphics modules rather than
scatter OS checks through rendering callers.

## Evidence log

### 2026-09-04: repository and host baseline

- Live `origin/dev` resolved to `3eb75a34babb48590954deb836a585fe8174a1d5`.
- The original checkout was `master` with only its user-owned untracked
  `GOAL.md`; the isolated worktree was created at
  `/Users/chesszyh987/Develop/danser-go-macos-port`.
- Go automatically supplied 1.26.1 for the module. Homebrew has SDL 3.4.14 and
  FFmpeg 9.0.1. Homebrew libyuv and macOS BASS libraries were not found in the
  initial dependency probe.
- Upstream bundles Windows DLLs and x86-64 Linux `.so` files, not Darwin dylibs.

### 2026-09-04: Darwin dependencies and build

- `tools/macos-deps.sh` stages Homebrew SDL3, official BASS/BASSmix/BASS FX
  universal dylibs, and an arm64 static libyuv built from pinned upstream
  revision `eb6e7bb63738e29efd82ea3cf2a115238a89fa51`.
- The Darwin cgo link paths resolve all three BASS dylibs and libyuv. `go build
  ./...` and `go build -o danser .` passed; `file danser` reports an arm64
  Mach-O executable.
- `go test -vet=off ./...` passed four tests across 97 packages. Normal `go
  test ./...` reaches vet and currently reports pre-existing printf-analyzer
  findings in the launcher and scoreboard; these must be corrected before the
  final audit.

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
