"""M9 launcher."""
from __future__ import annotations

import subprocess
import os
import sys
from pathlib import Path


APP = Path(__file__).resolve().parent / "app.py"


if __name__ == "__main__":
    raise SystemExit(subprocess.call([
        sys.executable,
        "-m", "streamlit", "run", str(APP),
        "--server.address", os.environ.get("STREAMLIT_SERVER_ADDRESS", "127.0.0.1"),
        "--server.port", os.environ.get("STREAMLIT_SERVER_PORT", "8501"),
        "--browser.gatherUsageStats", "false",
    ]))
