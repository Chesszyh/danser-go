#!/usr/bin/env python3
"""Follow official osu!lazer releases and publish only validated updates."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

STATE = Path('.github/lazer-update.json')
VERSION = re.compile(r'v(\d+)\.(\d+)\.(\d+)-lazer\.(\d+)')


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def api(endpoint, method='GET', **fields):
    command = ['gh', 'api', endpoint, '--method', method]
    if fields:
        command += ['--input', '-']
    return json.loads(run(*command, input=json.dumps(fields) if fields else None))


def next_tag(tags):
    versions = [tuple(map(int, m.groups())) for tag in tags if (m := VERSION.fullmatch(tag))]
    if not versions:
        raise ValueError('No vMAJOR.MINOR.PATCH-lazer.N tag exists')
    major, minor, patch, revision = max(versions)
    if revision >= 9998:
        raise ValueError('Fork revision limit reached; select a new base version')
    return f'v{major}.{minor}.{patch}-lazer.{revision + 1}'


def output(**values):
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        for key, value in values.items():
            stream.write(f'{key}={value}\n')


def prepare(repo):
    release = api('repos/ppy/osu/releases/latest')
    if release['draft'] or release['prerelease']:
        raise ValueError('Expected a published official osu!lazer release')
    osu_tag = release['tag_name']
    if not re.fullmatch(r'\d{4}\.\d{3,4}\.\d+-lazer', osu_tag):
        raise ValueError(f'Unexpected official release tag: {osu_tag!r}')
    run('git', '-C', 'third_party/osu', 'fetch', 'origin', f'refs/tags/{osu_tag}')
    target = run('git', '-C', 'third_party/osu', 'rev-parse', 'FETCH_HEAD^{commit}')
    current = run('git', '-C', 'third_party/osu', 'rev-parse', 'HEAD')
    ancestor = subprocess.run(['git', '-C', 'third_party/osu', 'merge-base', '--is-ancestor', target, current])
    if ancestor.returncode == 0:
        print(f'{osu_tag} is already included in the pinned source; no downgrade or release needed')
        output(changed='false')
        return
    if ancestor.returncode != 1:
        raise ValueError('Could not compare official release history')
    run('git', '-C', 'third_party/osu', 'merge-base', '--is-ancestor', current, target)
    base = run('git', 'rev-parse', 'origin/master')
    branch = 'automation/osu-lazer-' + osu_tag
    existing = run('git', 'ls-remote', '--heads', 'origin', branch)
    if existing:
        run('git', 'fetch', 'origin', branch)
        run('git', 'checkout', '-B', branch, 'FETCH_HEAD')
        run('git', '-c', 'user.name=Codex', '-c', 'user.email=codex@agent.invalid', 'merge', '--no-edit', 'origin/master')
        state = json.loads(STATE.read_text())
        if state['osuRelease'] != osu_tag:
            raise ValueError('Existing update branch belongs to a different release')
        run('git', 'submodule', 'update', '--init', '--recursive')
    else:
        run('git', 'checkout', '-b', branch, 'origin/master')
        tag = next_tag(run('git', 'tag', '--list').splitlines())
        run('git', '-C', 'third_party/osu', 'checkout', '--detach', target)
        run('git', '-C', 'third_party/osu', 'submodule', 'update', '--init', '--recursive')
        state = {'osuRelease': osu_tag, 'releaseTag': tag}
        STATE.write_text(json.dumps(state, indent=2) + '\n')
        notes = Path('docs/releases') / f'{tag}.md'
        notes.write_text(f'Update the official osu!lazer rules to [{osu_tag}]({release["html_url"]}).\n\n'
                         'Linux x86-64 and macOS arm64 include the official rules host. '
                         'New configurations use official lazer scoring; stable replays retain stable scoring.\n')
        run('git', 'add', 'third_party/osu', str(STATE), str(notes))
        run('git', '-c', 'user.name=Codex', '-c', 'user.email=codex@agent.invalid', 'commit',
            '--author=Codex <codex@agent.invalid>', '-m', f'Update official osu!lazer to {osu_tag}')
    run('git', 'push', 'origin', branch)
    pulls = api(f'repos/{repo}/pulls?state=open&head={repo.split("/")[0]}:{branch}&base=master')
    if pulls:
        pull = pulls[0]
    else:
        pull = api(f'repos/{repo}/pulls', 'POST', title=f'Update official osu!lazer to {osu_tag}',
                   head=branch, base='master', body=f'Updates the pinned official rules to {release["html_url"]}.\n\n'
                   'The Lazer update workflow builds and validates Linux and macOS before merging. '
                   'A failed check leaves this PR open and does not publish a release.')
    output(changed='true', revision=run('git', 'rev-parse', 'HEAD'), base=base,
           tag=state['releaseTag'], version=state['releaseTag'][1:], pr=pull['number'])
    print(pull['html_url'])


def finish(repo, pr, revision, base, tag):
    if not VERSION.fullmatch(tag):
        raise ValueError('Invalid fork release tag')
    pull = api(f'repos/{repo}/pulls/{pr}')
    if pull['head']['sha'] != revision:
        raise ValueError('PR changed after validation; run validation again')
    if pull['merged']:
        merged = pull['merge_commit_sha']
    else:
        if pull['state'] != 'open' or pull['base']['sha'] != base:
            raise ValueError('Base changed after validation; run the update workflow again')
        result = api(f'repos/{repo}/pulls/{pr}/merge', 'PUT', sha=revision, merge_method='merge',
                     commit_title=pull['title'])
        if not result['merged']:
            raise ValueError('PR was not merged')
        merged = result['sha']
    run('git', 'fetch', 'origin', 'master', '--tags')
    state = json.loads(run('git', 'show', f'{merged}:{STATE}'))
    if state['releaseTag'] != tag:
        raise ValueError('Merged source does not match the release tag')
    existing = subprocess.run(['git', 'rev-parse', '--verify', f'refs/tags/{tag}^{{commit}}'], capture_output=True, text=True)
    if existing.returncode == 0:
        if existing.stdout.strip() != merged:
            raise ValueError('Release tag already points to a different commit')
    else:
        run('git', '-c', 'user.name=Codex', '-c', 'user.email=codex@agent.invalid',
            'tag', '-a', tag, merged, '-m', f'danser {tag}')
        run('git', 'push', 'origin', f'refs/tags/{tag}')
    # GITHUB_TOKEN tag pushes do not trigger push workflows; dispatch explicitly.
    run('gh', 'workflow', 'run', 'release.yml', '--repo', repo, '--ref', tag)
    print(f'Dispatched Linux/macOS release {tag} from {merged}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'finish'])
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY', 'Chesszyh/danser-go'))
    parser.add_argument('--pr', type=int)
    parser.add_argument('--revision')
    parser.add_argument('--base')
    parser.add_argument('--tag')
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.repo)
    else:
        if not all([args.pr, args.revision, args.base, args.tag]):
            parser.error('finish requires --pr, --revision, --base and --tag')
        finish(args.repo, args.pr, args.revision, args.base, args.tag)


if __name__ == '__main__':
    main()
