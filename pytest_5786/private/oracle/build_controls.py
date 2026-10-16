#!/usr/bin/env python3
"""Rebuild this one eval's reviewed control diffs from fixed Git source versions."""
import argparse
import difflib
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
BASE = "955e54221008aba577ecbaefa15679f6777d3bf8"
MERGE = "01082fea12649384aab44306f49503de1374c4a1"
FILE = "src/_pytest/reports.py"


def main(repo):
    def source(commit):
        return subprocess.check_output(["git", "-C", str(repo), "show", commit + ":" + FILE], text=True)
    base, historical = source(BASE), source(MERGE)
    complete = historical.replace(
        "return reprcrash.__dict__.copy()", "return None if reprcrash is None else reprcrash.__dict__.copy()"
    ).replace("return ReprFileLocation(**repr_crash_dict)",
              "return None if repr_crash_dict is None else ReprFileLocation(**repr_crash_dict)")
    # A second codec preserves the old methods and recursively reuses their flat
    # representation. It uses a different chain wire shape from the reference.
    alternative = base.replace("from _pytest._code.code import ExceptionInfo",
                               "from _pytest._code.code import ExceptionChainRepr\nfrom _pytest._code.code import ExceptionInfo")
    alternative = alternative.replace("def disassembled_report(rep):", "def disassembled_report(longrepr, include_chain=True):")
    alternative = alternative.replace("rep.longrepr", "longrepr")
    alternative = alternative.replace("reprcrash = longrepr.reprcrash.__dict__.copy()",
        "reprcrash = None if longrepr.reprcrash is None else longrepr.reprcrash.__dict__.copy()")
    old = '''            return {
                "reprcrash": reprcrash,
                "reprtraceback": reprtraceback,
                "sections": longrepr.sections,
            }
'''
    new = old.replace("return {", "result = {") + '''            if include_chain and isinstance(longrepr, ExceptionChainRepr):
                result["causes"] = [
                    {"part": disassembled_report(ReprExceptionInfo(tb, crash), False), "link": link}
                    for tb, crash, link in longrepr.chain
                ]
            return result
'''
    assert old in alternative
    alternative = alternative.replace(old, new).replace("disassembled_report(self)", "disassembled_report(self.longrepr)")
    insertion = '''        payload = reportdict.get("longrepr")
        if isinstance(payload, dict) and "causes" in payload:
            chain = []
            for segment in payload["causes"]:
                partial = cls._from_json(dict(reportdict, longrepr=segment["part"]))
                chain.append((partial.longrepr.reprtraceback, partial.longrepr.reprcrash, segment["link"]))
            representation = ExceptionChainRepr(chain)
            for section in payload["sections"]:
                representation.addsection(*section)
            return cls(**dict(reportdict, longrepr=representation))

'''
    alternative = alternative.replace('        if reportdict["longrepr"]:', insertion + '        if reportdict["longrepr"]:')
    alternative = alternative.replace("reprcrash=ReprFileLocation(**reprcrash),",
                                      "reprcrash=None if reprcrash is None else ReprFileLocation(**reprcrash),")
    controls = {
        "noop": base, "historical": historical, "complete": complete, "alternative": alternative,
        "last_only": complete.replace("in rep.longrepr.chain:", "in rep.longrepr.chain[-1:]:"),
        "testreport_only": complete.replace("if isinstance(rep.longrepr, ExceptionChainRepr):",
            "if isinstance(rep.longrepr, ExceptionChainRepr) and isinstance(rep, TestReport):"),
        "text_only": base.replace('d["longrepr"] = disassembled_report(self)', 'd["longrepr"] = str(self.longrepr)'),
    }
    assert controls["last_only"] != complete and controls["testreport_only"] != complete
    for name, text in controls.items():
        diff = "".join(difflib.unified_diff(base.splitlines(True), text.splitlines(True),
                                          fromfile="a/" + FILE, tofile="b/" + FILE))
        if diff:
            diff = "diff --git a/{0} b/{0}\n".format(FILE) + diff
        (HERE / (name + ".patch")).write_text(diff)
    tests = subprocess.check_output(["git", "-C", str(repo), "diff", "--binary", BASE, MERGE, "--", "testing/"])
    (HERE / "historical_tests.patch").write_bytes(tests)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    main(parser.parse_args().repo)
