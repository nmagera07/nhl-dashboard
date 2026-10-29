"""
Builds the notifier function's deploy zip: notifier_function/ plus the
backend modules it imports. Used by the deploy workflow and by
setup_notifier_function.py. Prints the zip's path.

    python scripts/package_notifier.py [out.zip]
"""

import sys
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
MODULES = ("notify_live_games.py", "push.py", "market_odds.py", "goal_model.py", "logging_config.py",
           "pregame_briefs.py", "data_checks.py", "post_drafts.py")


def build(out):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted((BACKEND / "notifier_function").iterdir()):
            if path.is_file():
                z.write(path, path.name)
        for name in MODULES:
            z.write(BACKEND / name, name)
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1] if len(sys.argv) > 1 else "notifier.zip").resolve()))
