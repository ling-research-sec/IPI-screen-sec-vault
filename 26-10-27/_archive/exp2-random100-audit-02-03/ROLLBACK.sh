#!/bin/sh
set -eu
[ "$#" -eq 1 ] || exit 2
/opt/homebrew/opt/python@3.14/bin/python3.14 - "$1" <<'PYROLL'
from pathlib import Path
import sys,subprocess,hashlib
t=Path(sys.argv[1]).resolve();assert t.parent==Path('/Users/y4n9/Workspace/Projects/My-github-projects/IPI-screen-sec-vault/26-10-27/_archive/exp2-random100-audit-02-03')/"rollback-test"
r=subprocess.run(["patch","--quiet","-R",str(t),str(t.parent.parent/"notes.diff")],capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
assert hashlib.sha256(t.read_bytes()).hexdigest()=='8b7cab4dd5270842dacea3a1332090cf8f95b7c0b0ea5137b2e8cdd0d958dbd6'
print("ROLLBACK PASS: isolated document restored to pre-audit SHA256")
PYROLL
