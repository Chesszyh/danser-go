#!/bin/sh

set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
deps_dir=${DANSER_MACOS_DEPS_DIR:-"$repo_dir/.deps/macos"}
deps_dir=$(CDPATH= cd -- "$deps_dir" && pwd)
export DANSER_MACOS_DEPS_DIR="$deps_dir"
export DANSER_TEST_OPENGL=1
"$repo_dir/tools/macos-go.sh" test -p 1 -count=1 ./...
"$repo_dir/tools/macos-go.sh" run ./tools/gl41-smoke "$deps_dir"
