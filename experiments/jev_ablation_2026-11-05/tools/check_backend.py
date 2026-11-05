"""Check that a backend/ folder holds PR #77's decision code as the recorded set ran it (commit 3c936ae).

The runner imports eight files of that folder. This script compares each with the file at 3c936ae (sha256 of its
text with LF line ends, so a Windows checkout with CRLF and a Linux checkout both match) and prints the folder's git
commit. Equal files mean the rule table, the stages and the requests are the recorded ones, whatever the commit (for
example main after PR #77 is merged). No API call, no import of the PR code.

  python -B tools/check_backend.py --backend <checkout>/backend
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

# sha256 of each file's text at 3c936ae as git stores it (LF), from `git show 3c936ae:backend/<file>`
AT_3C936AE = {
    "app/modules/decision/schemas.py": "f7154b9851ec9b7906774c4467d30408a7289de603fd98b478b35a21a5b93f48",
    "app/modules/decision/rule_table.py": "d2e2b2fb04474419ea69976cdec5711796695dc943cc5b1ad1fd71802d10d323",
    "app/modules/decision/jev_questions.py": "fd844c362bffe7e977143abedd91686a8f1053b662d9473cb32effc1c9f515c7",
    "app/modules/decision/service.py": "98ab3f8a58b5da1788b3e54913f3558fa0e42c69b47ea5cfdb749f482d2a4ddd",
    "app/modules/decision/repository.py": "7e8832960f173f5f33eb9e942e843658321d4e6de081d6d8dce03b65f7cd57a9",
    "app/infrastructure/external/jev_client.py": "a03d1ae59b011c66785a03c33bcecc5402ef1e8bd0626beb903d738cead79a3d",
    "app/infrastructure/external/jev_schemas.py": "e7c50859d2e3adb0983e94e8446077ae893d4c15182842f0778975a296a0aa40",
    "app/common/config/settings.py": "4cd5482c534b363d543c0e9664d03511da2bdbc729875321727b554cf02bcc63",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backend", default=os.environ.get("E5_BACKEND"), help="default: the environment variable E5_BACKEND")
    args = ap.parse_args()
    if not args.backend:
        raise SystemExit("pass --backend <checkout>/backend or set E5_BACKEND")
    root = Path(args.backend)
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                                check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    print(f"backend {root}: git commit {commit or 'unknown (not a git checkout)'}")
    same = 0
    for f, want in AT_3C936AE.items():
        p = root / f
        if not p.is_file():
            print(f"  missing  {f}")
            continue
        got = hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        same += got == want
        print(f"  {'same    ' if got == want else 'DIFFERS '} {f}")
    print(f"{same} of {len(AT_3C936AE)} files equal to 3c936ae"
          + ("" if same == len(AT_3C936AE) else "; results may differ from the recorded set"))
    return 0 if same == len(AT_3C936AE) else 1


if __name__ == "__main__":
    sys.exit(main())
