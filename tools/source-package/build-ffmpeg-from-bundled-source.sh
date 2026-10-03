#!/bin/sh
# Use the verified tar stream and unmodified historical build flags.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
output=${1:-"$root/ffmpeg-rebuild"}
test "$(uname -s)" = Darwin || { echo 'Build this on macOS' >&2; exit 1; }
test ! -e "$output" || { echo 'Choose a new output directory' >&2; exit 1; }
archive="$root/upstream/ffmpeg-4.3.3.tar.xz"
expected=9f0a68fbd74feb4e50dc220bddd59d84626774a53687fb737806ae00e5c6e9e6
test "$(shasum -a 256 "$archive" | awk '{print $1}')" = "$expected"
mkdir -p "$output"
cp "$root/upstream/ffmpeg-build/"*.sh "$output/"
cd "$output"
xz -dc "$archive" | gzip -n > ffmpeg-4.3.3.tar.gz
arch=arm64 bash ./build-macOS.sh
arch=x86_64 bash ./build-macOS.sh
bash ./combine_dylibs.sh
echo "Built replacement universal dylibs in $output/macOS-universal"
