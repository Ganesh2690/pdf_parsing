"""
watch_and_update.py  —  Monitors extract_11.log and updates the report
when extraction completes (all rows written + Python process done).

Usage:  python watch_and_update.py
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
LOG = ROOT / "extract_11.log"
TOTAL_EXPECTED = 190  # 19 PDFs × 10 parsers
CHECK_INTERVAL = 30  # seconds between polls


def count_result_rows(path: Path) -> int:
    count = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    json.loads(line)
                    count += 1
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    return count


def python_still_running() -> bool:
    """Check if any extract_11 Python process is running."""
    try:
        # tasklist is available on Windows
        result = subprocess.run(
            ["tasklist", "/fi", "imagename eq python.exe", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "python.exe" in result.stdout
    except Exception:
        return False


def run_update():
    print("\n>>> Running update_report.py ...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "update_report.py")], capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:500])


def main():
    print(f"Watching {LOG}")
    print(f"Expected rows: {TOTAL_EXPECTED}  |  Check interval: {CHECK_INTERVAL}s")
    print("Ctrl-C to stop\n")

    last_count = -1
    done = False

    while not done:
        count = count_result_rows(LOG)
        still_running = python_still_running()

        if count != last_count:
            pct = count / TOTAL_EXPECTED * 100
            print(
                f"[{time.strftime('%H:%M:%S')}] Rows: {count}/{TOTAL_EXPECTED} "
                f"({pct:.0f}%)  Python alive: {still_running}"
            )
            # Intermediate update every 20 rows
            if count > 0 and count % 20 == 0 and count != last_count:
                run_update()
            last_count = count

        if count >= TOTAL_EXPECTED or (not still_running and count > 0):
            print(f"\n>>> Extraction finished! {count} rows found.")
            run_update()
            done = True
        else:
            time.sleep(CHECK_INTERVAL)

    print("Done.")


if __name__ == "__main__":
    main()
