#!/bin/sh

set -eu

if [ "$(uname -s)" != "Darwin" ]; then
	echo "macOS dependencies can only be prepared on macOS" >&2
	exit 1
fi

for tool in curl unzip tar cmake ninja file shasum; do
	if ! command -v "$tool" >/dev/null 2>&1; then
		echo "Required dependency tool is missing: $tool" >&2
		exit 1
	fi
done

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
deps_dir=${DANSER_MACOS_DEPS_DIR:-"$repo_dir/.deps/macos"}
archives_dir="$deps_dir/archives"
lib_dir="$deps_dir/lib"
libyuv_src="$deps_dir/src/libyuv"
libyuv_build="$deps_dir/build/libyuv"
sdl_src="$deps_dir/src/SDL3"
sdl_build="$deps_dir/build/SDL3"

mkdir -p "$archives_dir" "$lib_dir" "$libyuv_src" "$libyuv_build" "$sdl_src" "$sdl_build"

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

sdl_version=3.4.16
sdl_checksum=7322236cd12090c3eb40b9728be4d49c76f66ad17d04369584d4ecad5cf77c68
sdl_archive="$archives_dir/SDL3-$sdl_version.tar.gz"
download "https://github.com/libsdl-org/SDL/releases/download/release-$sdl_version/SDL3-$sdl_version.tar.gz" "$sdl_archive"

actual_sdl_checksum=$(shasum -a 256 "$sdl_archive" | awk '{print $1}')
if [ "$actual_sdl_checksum" != "$sdl_checksum" ]; then
	echo "SDL3 archive checksum mismatch: expected $sdl_checksum, got $actual_sdl_checksum" >&2
	exit 1
fi

if [ ! -f "$sdl_src/CMakeLists.txt" ]; then
	tar -xzf "$sdl_archive" -C "$sdl_src" --strip-components=1
fi

cmake -S "$sdl_src" -B "$sdl_build" -G Ninja \
	-DCMAKE_BUILD_TYPE=Release \
	-DCMAKE_OSX_ARCHITECTURES=arm64 \
	-DCMAKE_OSX_DEPLOYMENT_TARGET=11.0 \
	-DSDL_SHARED=ON \
	-DSDL_STATIC=OFF \
	-DSDL_TEST_LIBRARY=OFF \
	-DSDL_TESTS=OFF
cmake --build "$sdl_build" --target SDL3-shared
cp -f "$sdl_build/libSDL3.0.dylib" "$lib_dir/libSDL3.dylib"

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
	-DCMAKE_OSX_DEPLOYMENT_TARGET=11.0 \
	-DCMAKE_DISABLE_FIND_PACKAGE_JPEG=TRUE \
	-DUNIT_TEST=OFF \
	-DBUILD_SHARED_LIBS=OFF
cmake --build "$libyuv_build" --target yuv
cp "$libyuv_build/libyuv.a" "$lib_dir/libyuv.a"

file "$lib_dir"/*
