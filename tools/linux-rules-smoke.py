#!/usr/bin/env python3
"""Verify the actual Linux archive's official rules without a display server."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile


def main():
    repo = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location('smoke', repo / 'tools/macos-bundle-smoke.py')
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    archive = next((repo / 'dist/artifacts').glob('*.zip'))
    with tempfile.TemporaryDirectory(prefix='danser-linux-') as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive) as package:
            package.extractall(root)
            for member in package.infolist():
                if member.external_attr >> 16:
                    (root / member.filename).chmod((member.external_attr >> 16) & 0o777)
        env = dict(os.environ)
        env.pop('FFMPEG', None)
        subprocess.run(['sh', str(repo / 'tools/macos-smoke-fixture.sh')], env=env, check=True, timeout=120)
        fixture = repo / '.deps/macos/smoke/Songs/000 macOS Port Smoke Test'
        host = root / 'lazer-rules-host/danser-lazer-rules'
        revision = subprocess.check_output(['git', '-C', str(repo / 'third_party/osu'), 'rev-parse', 'HEAD'], text=True).strip()
        beatmap = fixture / 'macos-smoke.osu'
        object_count = sum(bool(line.strip()) and not line.startswith('//') for line in beatmap.read_text().split('[HitObjects]', 1)[1].splitlines())
        result = subprocess.run([str(host), 'rejudge', '--beatmap', str(beatmap), '--replay', str(fixture / 'macos-smoke-lazer.osr')],
                                env=env, text=True, capture_output=True, timeout=180, check=True)
        smoke.verify_rejudge(json.loads(result.stdout), revision, object_count)
        smoke.verify_live(host, beatmap, env, root, revision, object_count)
        print('Linux archive: official replay and live rules passed')


if __name__ == '__main__':
    main()
