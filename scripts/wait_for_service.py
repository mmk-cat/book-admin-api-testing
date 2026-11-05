"""Wait until a JSON HTTP endpoint returns 200 (used by Jenkins)."""

from __future__ import annotations

import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

url = sys.argv[1]
timeout_seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 60
deadline = time.time() + timeout_seconds
last_error = ""
while time.time() < deadline:
    try:
        with urlopen(url, timeout=3) as response:
            if response.status == 200:
                print(f"Service ready: {url}")
                raise SystemExit(0)
    except (URLError, TimeoutError, OSError) as exc:
        last_error = str(exc)
    time.sleep(2)
print(f"Service not ready after {timeout_seconds}s: {url} ({last_error})")
raise SystemExit(1)
