#!/bin/sh

set -eu

if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
	echo "The macOS build requires Apple Silicon macOS" >&2
	exit 1
fi

case "${1:-}" in
	build|test|run) go_command=$1; shift ;;
	*) echo "Usage: $0 build|test|run [go arguments...]" >&2; exit 2 ;;
esac

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
deps_dir=${DANSER_MACOS_DEPS_DIR:-"$repo_dir/.deps/macos"}
deps_dir=$(CDPATH= cd -- "$deps_dir" && pwd)

for library in libSDL3.dylib libbass.dylib libbass_fx.dylib libbassmix.dylib libyuv.a; do
	if [ ! -f "$deps_dir/lib/$library" ]; then
		echo "Missing $deps_dir/lib/$library; run tools/macos-deps.sh first" >&2
		exit 1
	fi
done

export DANSER_MACOS_DEPS_DIR="$deps_dir"
export CGO_ENABLED=1 GOOS=darwin GOARCH=arm64
export CGO_LDFLAGS="${CGO_LDFLAGS:-} \"-L$deps_dir/lib\" \"-Wl,-rpath,${DANSER_MACOS_RPATH:-$deps_dir/lib}\""

cd "$repo_dir"
exec go "$go_command" -tags "danser_external_deps ${DANSER_MACOS_GO_TAGS:-}" "$@"
