"""Adversarial source archives and trusted-baseline patch generation."""
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pilot'))
from common import REPO, load_runtime
from snapshot import extract, normalize_git_modes, FILE_LIMIT


class ArchiveTests(unittest.TestCase):
    def check_archive(self, entries, *, reject=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'source.tar'
            with tarfile.open(archive, 'w') as tar:
                for info, raw in entries:
                    tar.addfile(info, io.BytesIO(raw) if raw is not None else None)
            if reject:
                with self.assertRaises((ValueError, FileExistsError, NotADirectoryError)):
                    extract(archive, root/'snapshot')
            else:
                return extract(archive, root/'snapshot')

    def member(self, name='src/example.py', raw=b'x=1\n', kind=tarfile.REGTYPE):
        info = tarfile.TarInfo(name)
        info.size = len(raw) if kind == tarfile.REGTYPE else 0
        info.type, info.mode = kind, 0o644
        if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE): info.linkname = '/fake-private'
        return info, raw if kind == tarfile.REGTYPE else None

    def test_regular_source(self):
        self.assertEqual(self.check_archive([self.member()], reject=False)['src/example.py']['bytes'], 4)

    def test_symlink(self): self.check_archive([self.member(kind=tarfile.SYMTYPE)])
    def test_hardlink(self): self.check_archive([self.member(kind=tarfile.LNKTYPE)])
    def test_fifo(self): self.check_archive([self.member(kind=tarfile.FIFOTYPE)])
    def test_device(self): self.check_archive([self.member(kind=tarfile.CHRTYPE)])
    def test_traversal(self): self.check_archive([self.member('src/../../outside.py')])
    def test_absolute(self): self.check_archive([self.member('/src/evil.py')])
    def test_duplicate(self): self.check_archive([self.member(), self.member()])
    def test_large_file(self): self.check_archive([self.member(raw=b'x'*(FILE_LIMIT+1))])
    def test_total_limit(self): self.check_archive([self.member(f'src/f{i}.py',b'x'*FILE_LIMIT) for i in range(9)])
    def test_invalid_utf8(self): self.check_archive([self.member(raw=b'\xff')])
    def test_hidden_python(self): self.check_archive([self.member('src/.hidden.py')])
    def test_root_symlink(self): self.check_archive([self.member('src',kind=tarfile.SYMTYPE)])
    def test_parent_file(self): self.check_archive([self.member('src/x.py'),self.member('src/x.py/y.py')])

    def test_execute_bit_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('baseline','snapshot'):
                (root/name/'src').mkdir(parents=True)
                (root/name/'src/x.py').write_text('x=1')
                (root/name/'src/x.py').chmod(0o644)
            (root/'snapshot/src/x.py').chmod(0o755)
            with self.assertRaises(ValueError):
                normalize_git_modes(root/'snapshot',root/'baseline')


class TrustedBaselineTests(unittest.TestCase):
    def test_candidate_git_ignored_and_fresh_apply(self):
        Package, _, _, collect, assert_applied = load_runtime()
        package = Package(REPO/'pytest_5786', REPO.parent/'pytest')
        with tempfile.TemporaryDirectory(dir=REPO/'harbor/.cache') as directory:
            root = Path(directory)
            baseline = package.prepare(root/'candidate')
            # If candidate Git is invoked, this hook would create the marker.
            hooks = root/'candidate/.git/hooks'; hooks.mkdir(exist_ok=True)
            marker = root/'EXECUTED'
            (hooks/'pre-commit').write_text('#!/bin/sh\ntouch '+str(marker)+'\n')
            (hooks/'pre-commit').chmod(0o755)
            (root/'candidate/.git/config').write_text('[core]\n hooksPath = '+str(hooks)+'\n[diff]\n external = touch '+str(marker)+'\n')
            (root/'candidate/src/pilot_helper.py').write_text('VALUE = 42\n')
            record = collect(package, root/'candidate', baseline, root/'submission')
            self.assertFalse(marker.exists())
            self.assertEqual(record['changed_files'], ['src/pilot_helper.py'])
            package.prepare(root/'fresh')
            assert_applied(package, root/'submission/submission.patch', root/'fresh', record['source_sha256'])


if __name__ == '__main__': unittest.main()
