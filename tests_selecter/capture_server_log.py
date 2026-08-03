"""Start the real API briefly and retain an auditable server log artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default="reports/server.log")
    parser.add_argument("--manifest", default="reports/server_log_manifest.json")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    log_path = Path(args.log)
    manifest_path = Path(args.manifest)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update({"NUM_USERS": "100", "BASE_DELAY": "0", "PYTHONDONTWRITEBYTECODE": "1"})
    requests = []
    ready = False
    started = time.monotonic()

    with log_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "info",
            ],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
        )
        try:
            deadline = time.monotonic() + max(args.timeout, 1)
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen(f"{base_url}/api/health", timeout=2) as response:
                        requests.append({"path": "/api/health", "status": response.status})
                        ready = response.status == 200
                        if ready:
                            break
                except OSError:
                    time.sleep(0.25)
            if ready:
                for path in ("/api/metrics/db-size", "/openapi.json"):
                    with urllib.request.urlopen(f"{base_url}{path}", timeout=5) as response:
                        response.read()
                        requests.append({"path": path, "status": response.status})
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    content = log_path.read_bytes()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "capture_success": ready and all(item["status"] == 200 for item in requests),
        "ready": ready,
        "requests": requests,
        "server_exit_code": process.returncode,
        "shutdown_requested_by_capture": True,
        "capture_wall_time_sec": round(time.monotonic() - started, 3),
        "log_path": log_path.as_posix(),
        "log_bytes": len(content),
        "log_lines": len(content.splitlines()),
        "sha256": hashlib.sha256(content).hexdigest(),
        "credential_values_recorded": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {log_path} and {manifest_path}")
    return 0 if ready and all(item["status"] == 200 for item in requests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
