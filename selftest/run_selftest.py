# PowerShell-friendly version of run_selftest.sh (no bash needed).
# Start the service on localhost:8000 first, then from the project folder:
#   python selftest\run_selftest.py
import os
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
os.chdir(here)
sys.path.insert(0, str(here))

from grader.grade_service import run
from grader._svc import wake, format_report

base = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
if not wake(base, "/", timeout=20):
    print(f"Service unreachable at {base} - start it, then re-run.")
    sys.exit(1)
print(format_report(run(base, "./data/selftest")))
