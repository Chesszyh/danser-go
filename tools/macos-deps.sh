#!/bin/sh

set -eu

if [ "$(uname -s)" != "Darwin" ]; then
	echo "macOS dependencies can only be prepared on macOS" >&2
	exit 1
fi

for tool in curl unzip tar cmake ninja file shasum git; do
	if ! command -v "$tool" >/dev/null 2>&1; then
		echo "Required dependency tool is missing: $tool" >&2
		exit 1
	fi
done

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
deps_dir=${DANSER_MACOS_DEPS_DIR:-"$repo_dir/.deps/macos"}
archives_dir="$deps_dir/archives"
lib_dir="$deps_dir/lib"
licenses_dir="$deps_dir/licenses"
sdl_version=3.4.16
sdl_checksum=7322236cd12090c3eb40b9728be4d49c76f66ad17d04369584d4ecad5cf77c68
libyuv_revision=eb6e7bb63738e29efd82ea3cf2a115238a89fa51
libyuv_src="$deps_dir/src/libyuv-$libyuv_revision"
libyuv_build="$deps_dir/build/libyuv-$libyuv_revision"
sdl_src="$deps_dir/src/SDL3-$sdl_version"
sdl_build="$deps_dir/build/SDL3-$sdl_version"

mkdir -p "$archives_dir" "$lib_dir" "$licenses_dir" "$libyuv_src" "$libyuv_build" "$sdl_src" "$sdl_build"

valid_archive() {
	archive=$1
	archive_name=$2
	checksum=${3:-}
	[ -s "$archive" ] || return 1
	if [ -n "$checksum" ]; then
		[ "$(shasum -a 256 "$archive" | awk '{print $1}')" = "$checksum" ] || return 1
	fi
	case "$archive_name" in
		*.zip) unzip -tq "$archive" >/dev/null 2>&1 ;;
		*.tar.gz) tar -tzf "$archive" >/dev/null 2>&1 ;;
		*) return 1 ;;
	esac
}

download() (
	url=$1
	destination=$2
	expected_checksum=${3:-}
	if valid_archive "$destination" "$destination" "$expected_checksum"; then
		return 0
	fi
	# Never expose an interrupted download as a reusable cache entry.
	temporary=$(mktemp "$destination.partial.XXXXXX")
	trap 'rm -f "$temporary"' EXIT HUP INT TERM
	curl -fL --retry 4 --retry-all-errors --retry-delay 2 \
		--connect-timeout 20 --max-time 180 "$url" -o "$temporary"
	if ! valid_archive "$temporary" "$destination" "$expected_checksum"; then
		echo "Dependency archive failed integrity validation: $url" >&2
		return 1
	fi
	mv -f "$temporary" "$destination"
)

extract_archive() (
	archive=$1
	destination=$2
	strip_components=$3
	archive_checksum=$(shasum -a 256 "$archive" | awk '{print $1}')
	if [ -f "$destination/.archive-sha256" ] && \
		[ "$(cat "$destination/.archive-sha256")" = "$archive_checksum" ]; then
		return 0
	fi
	temporary=$(mktemp -d "$destination.partial.XXXXXX")
	trap 'rm -rf "$temporary"' EXIT HUP INT TERM
	tar -xzf "$archive" -C "$temporary" --strip-components="$strip_components"
	[ -f "$temporary/CMakeLists.txt" ]
	printf '%s\n' "$archive_checksum" > "$temporary/.archive-sha256"
	rm -rf "$destination"
	mv "$temporary" "$destination"
)

checkout_git_source() (
	url=$1
	revision=$2
	destination=$3
	if [ -d "$destination/.git" ] && \
		[ "$(git -C "$destination" rev-parse HEAD)" = "$revision" ] && \
		[ -z "$(git -C "$destination" status --porcelain)" ]; then
		return 0
	fi
	temporary=$(mktemp -d "$destination.partial.XXXXXX")
	trap 'rm -rf "$temporary"' EXIT HUP INT TERM
	git -C "$temporary" init -q
	attempt=1
	until git -C "$temporary" fetch --no-tags --depth=1 "$url" "$revision"; do
		[ "$attempt" -lt 3 ] || return 1
		attempt=$((attempt + 1))
		sleep 2
	done
	git -C "$temporary" checkout --detach -q FETCH_HEAD
	[ "$(git -C "$temporary" rev-parse HEAD)" = "$revision" ]
	[ -f "$temporary/CMakeLists.txt" ]
	rm -rf "$destination"
	mv "$temporary" "$destination"
)

# Official archives verified on 2026-10-03. Fail closed if a rolling URL changes.
download "https://www.un4seen.com/files/bass24-osx.zip" "$archives_dir/bass.zip" \
	dfadd6238896b02b144b2870655fb9ee2445fc84d5c00f7e1c56faf9343ce59c
download "https://www.un4seen.com/files/bassmix24-osx.zip" "$archives_dir/bassmix.zip" \
	66b41300bed9868c203950cbec7641e89a56a088931e6b8125bf3011149cee69
download "https://www.un4seen.com/files/z/0/bass_fx24-osx.zip" "$archives_dir/bass_fx.zip" \
	eb9e496da229cdd73dc51d16c7e3fd17c7400a8125c2be2feb88eee1ac68dc68

unzip -joq "$archives_dir/bass.zip" libbass.dylib -d "$lib_dir"
unzip -joq "$archives_dir/bassmix.zip" libbassmix.dylib -d "$lib_dir"
unzip -joq "$archives_dir/bass_fx.zip" libbass_fx.dylib -d "$lib_dir"
unzip -p "$archives_dir/bass.zip" bass.txt > "$licenses_dir/BASS.txt"
unzip -p "$archives_dir/bassmix.zip" bassmix.txt > "$licenses_dir/BASSmix.txt"
unzip -p "$archives_dir/bass_fx.zip" bass_fx.txt > "$licenses_dir/BASS_FX.txt"

sdl_archive="$archives_dir/SDL3-$sdl_version.tar.gz"
download "https://github.com/libsdl-org/SDL/releases/download/release-$sdl_version/SDL3-$sdl_version.tar.gz" "$sdl_archive" "$sdl_checksum"
extract_archive "$sdl_archive" "$sdl_src" 1
cp "$sdl_src/LICENSE.txt" "$licenses_dir/SDL3-LICENSE.txt"

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

# Gitiles generates archives dynamically; compressed archive bytes are not a
# stable integrity identifier. Verify the pinned Git commit instead.
checkout_git_source "https://chromium.googlesource.com/libyuv/libyuv" "$libyuv_revision" "$libyuv_src"
cp "$libyuv_src/LICENSE" "$licenses_dir/libyuv-LICENSE.txt"
cp "$libyuv_src/PATENTS" "$licenses_dir/libyuv-PATENTS.txt"
cp "$libyuv_src/AUTHORS" "$licenses_dir/libyuv-AUTHORS.txt"

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
