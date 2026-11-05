"""Run the suite, record wall-clock regression time, then refresh metrics."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    started = time.perf_counter()
    command = [sys.executable, "-m", "pytest", *sys.argv[1:]]
    process = subprocess.run(command, cwd=ROOT)
    elapsed = time.perf_counter() - started
    (REPORTS / "run_meta.json").write_text(
        json.dumps(
            {
                "command": " ".join(command),
                "started_at": started_at,
                "elapsed_seconds": round(elapsed, 2),
                "exit_code": process.returncode,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    subprocess.run([sys.executable, str(ROOT / "scripts" / "collect_metrics.py")], cwd=ROOT)
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
