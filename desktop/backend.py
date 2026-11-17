"""Start the packaged backend under the machine's Python installation."""

from pathlib import Path
import sys

resources = Path(__file__).resolve().parent
sys.path[:0] = [str(resources), str(resources / "site-packages")]

from plate.__main__ import main  # noqa: E402

raise SystemExit(main())
