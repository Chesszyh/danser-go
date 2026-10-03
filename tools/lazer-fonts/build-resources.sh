#!/bin/bash
set -euo pipefail

if [[ $(uname -s) != Darwin || $(uname -m) != arm64 ]]; then
  echo 'Build the macOS resource package on Apple Silicon macOS' >&2
  exit 1
fi
repo_dir=$(cd "$(dirname "$0")/../.." && pwd)
work=${DANSER_LAZER_RESOURCES_DIR:-"$repo_dir/.deps/lazer-resources"}
revision=742ca60d4e7273dce0cac2fced7cd132f26f11c8
dotnet_cmd=${DOTNET:-dotnet}
mkdir -p "$work/upstream" "$work/feed" "$work/packages"
work=$(cd "$work" && pwd)
if [[ ! -d "$work/upstream/.git" ]]; then
  git -C "$work/upstream" init -q
fi
if [[ $(git -C "$work/upstream" rev-parse HEAD 2>/dev/null || true) != "$revision" ]]; then
  git -C "$work/upstream" fetch --no-tags --depth=1 https://github.com/ppy/osu-resources.git "$revision"
  git -C "$work/upstream" checkout --detach -q FETCH_HEAD
fi
[[ $(git -C "$work/upstream" rev-parse HEAD) == "$revision" ]]
rm -rf "$work/source" "$work/build" "$work/feed" "$work/packages/ppy.osu.game.resources/2026.909.0"
mkdir -p "$work/source" "$work/feed"
git -C "$work/upstream" archive "$revision" | tar -xf - -C "$work/source"
python3 "$repo_dir/tools/lazer-fonts/replace_restricted_fonts.py" apply "$work/source"
python3 "$repo_dir/tools/lazer-fonts/replace_restricted_fonts.py" audit "$work/source" > "$work/source-audit.json"

python3 - "$work" <<'PY'
from pathlib import Path
import sys, xml.etree.ElementTree as ET
w=Path(sys.argv[1]); root=ET.Element('configuration')
sources=ET.SubElement(root,'packageSources');ET.SubElement(sources,'clear')
ET.SubElement(sources,'add',key='rebuilt-resources',value=str(w/'feed'))
ET.SubElement(sources,'add',key='nuget.org',value='https://api.nuget.org/v3/index.json')
mapping=ET.SubElement(root,'packageSourceMapping')
ET.SubElement(ET.SubElement(mapping,'packageSource',key='rebuilt-resources'),'package',pattern='ppy.osu.Game.Resources')
ET.SubElement(ET.SubElement(mapping,'packageSource',key='nuget.org'),'package',pattern='*')
ET.ElementTree(root).write(w/'NuGet.Config',encoding='utf-8',xml_declaration=True)
PY

DOTNET_CLI_TELEMETRY_OPTOUT=1 "$dotnet_cmd" pack \
  "$work/source/osu.Game.Resources/osu.Game.Resources.csproj" --configuration Release \
  --output "$work/feed" -p:Version=2026.909.0 \
  -p:RepositoryUrl=https://github.com/Chesszyh/danser-go \
  -p:RepositoryCommit="$(git -C "$repo_dir" rev-parse HEAD)" \
  -p:BaseOutputPath="$work/build/bin/" -p:BaseIntermediateOutputPath="$work/build/obj/" \
  -p:RestorePackagesPath="$work/packages" -p:RestoreConfigFile="$work/NuGet.Config" -m:2

python3 "$repo_dir/tools/lazer-fonts/replace_restricted_fonts.py" audit "$work/source"
python3 - "$work" <<'PY'
from pathlib import Path
import hashlib,json,sys,zipfile
w=Path(sys.argv[1]);p=w/'feed/ppy.osu.Game.Resources.2026.909.0.nupkg'
with zipfile.ZipFile(p) as z:
    dll=z.read('lib/net8.0/osu.Game.Resources.dll')
d={'package':'ppy.osu.Game.Resources/2026.909.0','modified':True,'replacementFont':'Inter',
   'upstreamCommit':'742ca60d4e7273dce0cac2fced7cd132f26f11c8',
   'packageSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'assemblySha256':hashlib.sha256(dll).hexdigest()}
(w/'rebuilt-package.json').write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps(d))
PY
