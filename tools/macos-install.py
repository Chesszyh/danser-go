#!/usr/bin/env python3
"""Install a Danser macOS release, retaining the previous app until startup passes."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.request


APPLICATION = Path("/Applications/danser.app")


def run(*args):
    subprocess.run(args, check=True, timeout=180)


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def check_startup(app, home, logfile, keep=False):
    with logfile.open('w') as stream:
        process = subprocess.Popen([str(app / 'Contents/MacOS/danser')],
                                   env=dict(os.environ, HOME=str(home)),
                                   stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        success = False
        try:
            time.sleep(15)
            log = logfile.read_text()
            if process.poll() is not None or 'panic:' in log or 'Launcher crashed' in log:
                raise RuntimeError('Launcher failed startup:\n' + log[-4000:])
            if 'DatabaseManager: Loaded' not in log or 'BASS Initialized!' not in log:
                raise RuntimeError('Launcher did not finish initialization:\n' + log[-4000:])
            success = True
            return process.pid
        finally:
            if not keep or not success:
                stop(process)


def stop_installed_launcher(app):
    binary = str(app / 'Contents/MacOS/danser')
    matches = subprocess.run(['pgrep', '-f', '^' + re.escape(binary) + '$'], capture_output=True, text=True)
    if matches.returncode not in (0, 1):
        raise RuntimeError('Could not inspect running launcher')
    for value in matches.stdout.splitlines():
        pid = int(value)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    deadline = time.monotonic() + 10
    while matches.stdout and time.monotonic() < deadline:
        matches = subprocess.run(['pgrep', '-f', '^' + re.escape(binary) + '$'], capture_output=True, text=True)
        if matches.returncode == 1:
            return
        time.sleep(0.2)
    if matches.stdout:
        raise RuntimeError('Close the running Danser launcher, then rerun the installer')


def install(tag, archive=None):
    if not re.fullmatch(r'v\d+\.\d+\.\d+-lazer\.\d+', tag):
        raise ValueError('Expected a vMAJOR.MINOR.PATCH-lazer.N tag')
    if os.uname().sysname != 'Darwin' or os.uname().machine != 'arm64':
        raise ValueError('The release requires Apple Silicon macOS')
    signer = shutil.which('local-codesign') or str(Path.home() / '.local/bin/local-codesign')
    if not Path(signer).is_file():
        raise ValueError('local-codesign is required for local installation')
    installed = APPLICATION
    # Keep staging and backup on the destination volume for atomic renames.
    with tempfile.TemporaryDirectory(prefix='.danser-update-', dir=installed.parent) as temporary:
        work = Path(temporary)
        if archive:
            package = Path(archive).resolve(strict=True)
        else:
            package = work / 'danser-macos.zip'
            url = f'https://github.com/Chesszyh/danser-go/releases/download/{tag}/danser-macos.zip'
            with urllib.request.urlopen(url, timeout=60) as response, package.open('wb') as stream:
                shutil.copyfileobj(response, stream, length=1024 * 1024)
        staged = work / 'staged'
        run('ditto', '-x', '-k', str(package), str(staged))
        app = staged / 'danser.app'
        run('codesign', '--verify', '--deep', '--strict', str(app))
        version = subprocess.check_output(['go', 'version', '-m', str(app / 'Contents/MacOS/danser-cli')], text=True)
        if not any(line.split() == ['mod', 'github.com/wieku/danser-go', tag] for line in version.splitlines()):
            raise ValueError('Downloaded application version does not match the requested release')
        run(signer, str(app))
        run('codesign', '--verify', '--deep', '--strict', str(app))
        home = work / 'test-home'
        settings = home / 'Library/Application Support/danser/settings'
        settings.mkdir(parents=True)
        songs = work / 'test-songs'
        songs.mkdir()
        (settings / 'default.json').write_text(json.dumps({'General': {'OsuSongsDir': str(songs)}}))
        check_startup(app, home, work / 'isolated-startup.log')
        stop_installed_launcher(installed)
        backup = work / 'previous.app'
        had_previous = installed.exists()
        if had_previous:
            installed.rename(backup)
        try:
            app.rename(installed)
            run('codesign', '--verify', '--deep', '--strict', str(installed))
            pid = check_startup(installed, Path.home(), work / 'installed-startup.log', keep=True)
        except BaseException:
            if installed.exists():
                shutil.rmtree(installed)
            if had_previous:
                backup.rename(installed)
                subprocess.run(['open', '-a', str(installed)], check=False)
            raise
        print(f'Installed {tag}; startup passed with existing settings (PID {pid})')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    install(args.tag, args.archive)


if __name__ == '__main__':
    main()
