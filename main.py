

import sys
from pathlib import Path

# Allow running straight from a source checkout without `pip install -e .`.
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from figma_to_sitecore.cli import main  # noqa: E402

# `__name__ == "main"` covers `python -m main.py`: Python first imports this
# file as module "main" while looking for a ".py" submodule, so the pipeline
# still starts (and exits) during that import.
if __name__ in {"__main__", "main"}:
    main()
