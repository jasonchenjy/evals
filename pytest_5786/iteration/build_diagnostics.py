"""Three reviewed coding mistakes relative to the complete control; no model calls."""
import difflib
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
REPO = EVAL.parent.parent / 'pytest'
BASE = '955e54221008aba577ecbaefa15679f6777d3bf8'
FILE = 'src/_pytest/reports.py'


def main():
    original = subprocess.check_output(['git', '-C', str(REPO), 'show', BASE + ':' + FILE], text=True)
    with tempfile.TemporaryDirectory(prefix='stage4-controls-') as folder:
        path = Path(folder) / FILE
        path.parent.mkdir(parents=True)
        path.write_text(original)
        subprocess.run(['git', 'apply', str(EVAL / 'private/oracle/complete.patch')], cwd=folder, check=True)
        complete = path.read_text()
    replacements = {
        # Mistaking every structured exception representation for a chain.
        'chain_assumed': ('if isinstance(rep.longrepr, ExceptionChainRepr):',
                          'if hasattr(rep.longrepr, "reprtraceback"):'),
        # Keeping the exception data but forgetting the edge relationship text.
        'links_omitted': ('                        serialize_repr_crash(repr_crash),\n                        description,\n',
                          '                        serialize_repr_crash(repr_crash),\n                        None,\n'),
        # Reconstructing an exception object but forgetting its attached sections.
        'sections_omitted': ('        for section in reportdict["longrepr"]["sections"]:',
                             '        for section in []:'),
    }
    target = HERE / 'controls'
    target.mkdir(exist_ok=True)
    for name, (old, new) in replacements.items():
        assert complete.count(old) == 1, name
        altered = complete.replace(old, new, 1)
        diff = 'diff --git a/{0} b/{0}\n'.format(FILE) + ''.join(difflib.unified_diff(
            original.splitlines(True), altered.splitlines(True), fromfile='a/' + FILE, tofile='b/' + FILE))
        (target / (name + '.patch')).write_text(diff)
        print(name)


if __name__ == '__main__':
    main()
