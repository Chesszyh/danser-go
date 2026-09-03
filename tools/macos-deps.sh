#!/bin/sh

set -eu

if [ "$(uname -s)" != "Darwin" ]; then
	echo "macOS dependencies can only be prepared on macOS" >&2
	exit 1
fi

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
deps_dir=${DANSER_MACOS_DEPS_DIR:-"$repo_dir/.deps/macos"}
archives_dir="$deps_dir/archives"
lib_dir="$deps_dir/lib"
libyuv_src="$deps_dir/src/libyuv"
libyuv_build="$deps_dir/build/libyuv"

mkdir -p "$archives_dir" "$lib_dir" "$libyuv_src" "$libyuv_build"

download() {
	url=$1
	destination=$2
	if [ ! -f "$destination" ]; then
		curl -fL --retry 3 "$url" -o "$destination"
	fi
}

download "https://www.un4seen.com/files/bass24-osx.zip" "$archives_dir/bass.zip"
download "https://www.un4seen.com/files/bassmix24-osx.zip" "$archives_dir/bassmix.zip"
download "https://www.un4seen.com/files/z/0/bass_fx24-osx.zip" "$archives_dir/bass_fx.zip"

unzip -joq "$archives_dir/bass.zip" libbass.dylib -d "$lib_dir"
unzip -joq "$archives_dir/bassmix.zip" libbassmix.dylib -d "$lib_dir"
unzip -joq "$archives_dir/bass_fx.zip" libbass_fx.dylib -d "$lib_dir"

if ! command -v brew >/dev/null 2>&1 || ! sdl_prefix=$(brew --prefix sdl3 2>/dev/null); then
	echo "SDL3 is required; install it with: brew install sdl3" >&2
	exit 1
fi
cp -fL "$sdl_prefix/lib/libSDL3.dylib" "$lib_dir/libSDL3.dylib"

libyuv_revision=eb6e7bb63738e29efd82ea3cf2a115238a89fa51
libyuv_archive="$archives_dir/libyuv-$libyuv_revision.tar.gz"
download "https://chromium.googlesource.com/libyuv/libyuv/+archive/$libyuv_revision.tar.gz" "$libyuv_archive"

if [ ! -f "$libyuv_src/CMakeLists.txt" ]; then
	tar -xzf "$libyuv_archive" -C "$libyuv_src"
fi

cmake -S "$libyuv_src" -B "$libyuv_build" -G Ninja \
	-DCMAKE_BUILD_TYPE=Release \
	-DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
	-DCMAKE_OSX_ARCHITECTURES=arm64 \
	-DCMAKE_DISABLE_FIND_PACKAGE_JPEG=TRUE \
	-DUNIT_TEST=OFF \
	-DBUILD_SHARED_LIBS=OFF
cmake --build "$libyuv_build" --target yuv
cp "$libyuv_build/libyuv.a" "$lib_dir/libyuv.a"

file "$lib_dir"/*
