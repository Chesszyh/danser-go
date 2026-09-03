#!/bin/sh

set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
set_dir="$repo_dir/.deps/macos/smoke/Songs/000 macOS Port Smoke Test"
ffmpeg_bin=${FFMPEG:-$(command -v ffmpeg)}

mkdir -p "$set_dir"
cp "$repo_dir/tools/testdata/macos-smoke.osu" "$set_dir/macos-smoke.osu"

"$ffmpeg_bin" -hide_banner -loglevel error -y -threads 1 \
  -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=75" \
  -c:a pcm_s16le "$set_dir/audio.wav"

"$ffmpeg_bin" -hide_banner -loglevel error -y -threads 1 \
  -f lavfi -i "color=c=0x10182b:s=1280x720" -frames:v 1 \
  -vf "drawgrid=w=80:h=80:t=2:c=0x355080" "$set_dir/background.png"

"$ffmpeg_bin" -hide_banner -loglevel error -y -threads 1 \
  -f lavfi -i "color=c=0xe35d6a@0.85:s=128x128" -frames:v 1 \
  "$set_dir/storyboard.png"

go run "$repo_dir/tools/macos-smoke-replay" \
  "$set_dir/macos-smoke.osu" "$set_dir/macos-smoke.osr"

printf '%s\n' "$set_dir"
