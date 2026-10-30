import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('macos-install.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class InstallTests(unittest.TestCase):
    def attempt(self, installed_result):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / 'danser.app'
            app.mkdir()
            (app / 'version').write_text('old')
            archive = root / 'package.zip'
            archive.touch()
            signer = root / 'local-codesign'
            signer.touch()
            def fake_run(*args):
                if args[0] == 'ditto':
                    staged = Path(args[-1]) / 'danser.app'
                    staged.mkdir(parents=True)
                    (staged / 'version').write_text('new')
            with patch.object(m, 'APPLICATION', app), patch.object(m.os, 'uname', return_value=SimpleNamespace(sysname='Darwin', machine='arm64')), \
                    patch.object(m.shutil, 'which', return_value=str(signer)), patch.object(m, 'run', side_effect=fake_run), \
                    patch.object(m, 'stop_installed_launcher'), patch.object(m.subprocess, 'check_output', return_value='\tmod\tgithub.com/wieku/danser-go\tv0.12.1-lazer.5\n'), \
                    patch.object(m.subprocess, 'run'), patch.object(m, 'check_startup', side_effect=[123, installed_result]):
                if isinstance(installed_result, Exception):
                    with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                        m.install('v0.12.1-lazer.5', archive)
                    self.assertEqual((app / 'version').read_text(), 'old')
                else:
                    m.install('v0.12.1-lazer.5', archive)
                    self.assertEqual((app / 'version').read_text(), 'new')
                self.assertEqual(sorted(p.name for p in root.iterdir()), ['danser.app', 'local-codesign', 'package.zip'])

    def test_failed_startup_restores_previous_application(self):
        self.attempt(RuntimeError('startup failed'))

    def test_success_cleans_previous_application(self):
        self.attempt(456)


if __name__ == '__main__':
    unittest.main()
