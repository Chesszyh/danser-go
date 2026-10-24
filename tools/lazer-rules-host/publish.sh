#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <runtime> <output-directory>" >&2
    exit 2
fi
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
runtime=$1
mkdir -p "$2"
output=$(CDPATH= cd -- "$2" && pwd)
dotnet_cmd=${DOTNET:-dotnet}
resources_dir=${DANSER_LAZER_RESOURCES_DIR:-"$repo_dir/.deps/lazer-resources"}
export DANSER_LAZER_RESOURCES_DIR="$resources_dir"

bash "$repo_dir/tools/lazer-fonts/build-resources.sh"
cd "$repo_dir/third_party/osu"
"$dotnet_cmd" publish "$repo_dir/tools/lazer-rules-host/Danser.LazerRulesHost.csproj" \
    --configuration Release --runtime "$runtime" --self-contained true \
    --output "$output" \
    -p:RestorePackagesPath="$resources_dir/packages" \
    -p:RestoreConfigFile="$resources_dir/NuGet.Config" -m:2

python3 - "$resources_dir" "$output" <<'PY'
import hashlib, json, sys
from pathlib import Path
work, host = map(Path, sys.argv[1:])
expected = json.loads((work / 'rebuilt-package.json').read_text())
actual = hashlib.sha256((host / 'osu.Game.Resources.dll').read_bytes()).hexdigest()
assert actual == expected['assemblySha256'], 'Publish did not use the rebuilt Inter resource assembly'
PY
mkdir -p "$output/LazerFonts"
cp "$resources_dir/source/osu.Game.Resources/Fonts/OPEN_FONT_PROVENANCE.json" \
    "$resources_dir/source/osu.Game.Resources/Fonts/OPEN_FONT_SUBSTITUTIONS.txt" \
    "$resources_dir/source/osu.Game.Resources/Fonts/Inter/OFL.txt" \
    "$repo_dir/tools/lazer-fonts/pinned-resource-lock.json.gz" \
    "$resources_dir/rebuilt-package.json" "$output/LazerFonts/"
cp "$repo_dir/third_party/osu/LICENCE" "$output/osu-LICENCE"
cp "$resources_dir/source/LICENCE.md" "$output/LazerFonts/osu-resources-LICENCE.md"
