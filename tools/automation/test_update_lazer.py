#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('updater', Path(__file__).with_name('update-lazer.py'))
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
SHA = 'a' * 40
BASE = 'b' * 40


class UpdateTests(unittest.TestCase):
    def test_next_revision(self):
        self.assertEqual(u.next_tag(['macos-2026.10.03', 'v0.12.1-lazer.4', 'v0.12.1-lazer.10']), 'v0.12.1-lazer.11')
        self.assertEqual(u.next_tag(['v0.12.1-lazer.10', 'v0.12.2-lazer.1']), 'v0.12.2-lazer.2')
        with self.assertRaises(ValueError):
            u.next_tag(['v0.12.1-lazer.9998'])

    def test_changed_head_cannot_merge(self):
        pull = {'head': {'sha': 'changed'}}
        with patch.object(u, 'api', return_value=pull) as api, patch.object(u, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'changed after validation'):
                u.finish('owner/repo', 1, SHA, BASE, 'v0.12.1-lazer.5')
            api.assert_called_once()
            run.assert_not_called()

    def test_changed_base_cannot_merge(self):
        pull = {'head': {'sha': SHA}, 'merged': False, 'state': 'open', 'base': {'sha': 'changed'}}
        with patch.object(u, 'api', return_value=pull) as api, patch.object(u, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Base changed'):
                u.finish('owner/repo', 1, SHA, BASE, 'v0.12.1-lazer.5')
            api.assert_called_once()
            run.assert_not_called()

    def test_older_official_release_is_not_a_downgrade(self):
        release = {'draft': False, 'prerelease': False, 'tag_name': '2026.1005.0-lazer'}
        with patch.object(u, 'api', return_value=release), patch.object(u, 'run', return_value=SHA) as run, \
                patch.object(u.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(u, 'output') as output:
            u.prepare('owner/repo')
            output.assert_called_once_with(changed='false')
            self.assertFalse(any('push' in call.args for call in run.call_args_list))

    def test_prerelease_is_not_followed(self):
        with patch.object(u, 'api', return_value={'draft': False, 'prerelease': True}), patch.object(u, 'run') as run:
            with self.assertRaises(ValueError):
                u.prepare('owner/repo')
            run.assert_not_called()

    def test_merge_tags_validated_commit_and_dispatches_release(self):
        pull = {'head': {'sha': SHA}, 'merged': False, 'state': 'open', 'base': {'sha': BASE}, 'title': 'Update official rules'}
        merged = 'c' * 40
        def fake_run(*args, **kwargs):
            if args[:3] == ('git', 'show', f'{merged}:{u.STATE}'):
                return '{"releaseTag":"v0.12.1-lazer.5"}'
            return ''
        with patch.object(u, 'api', side_effect=[pull, {'merged': True, 'sha': merged}]) as api, \
                patch.object(u, 'run', side_effect=fake_run) as run, \
                patch.object(u.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
            u.finish('owner/repo', 1, SHA, BASE, 'v0.12.1-lazer.5')
            self.assertEqual(api.call_args_list[1].kwargs['sha'], SHA)
            self.assertTrue(any(call.args[:3] == ('git', 'push', 'origin') for call in run.call_args_list))
            self.assertEqual(run.call_args.args, ('gh', 'workflow', 'run', 'release.yml', '--repo', 'owner/repo', '--ref', 'v0.12.1-lazer.5'))


if __name__ == '__main__':
    unittest.main()
