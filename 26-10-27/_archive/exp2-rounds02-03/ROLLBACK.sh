#!/bin/sh
set -eu
[ "$#" -eq 1 ] || { echo "Usage: ROLLBACK.sh /absolute/disposable-config.json"; exit 2; }
"/opt/homebrew/bin/python3" - "$1" <<'PYROLL'
from pathlib import Path
import sys,hashlib
s=Path('/Users/y4n9/Workspace/Projects/My-github-projects/IPI-screen-sec-vault/26-10-27/_archive/exp2-process/config-full.json');t=Path(sys.argv[1]).resolve();assert t.parent==Path('/Users/y4n9/Workspace/Projects/My-github-projects/IPI-screen-sec-vault/26-10-27/_archive/exp2-rounds02-03')/"rollback-test";assert hashlib.sha256(s.read_bytes()).hexdigest()=='cab679744b765dc7cd5395e659d0c25f58e1f74e4e9f629b6a744d627eff48fb';t.write_bytes(s.read_bytes());print("ROLLBACK PASS: disposable configuration restored to round01")
PYROLL
