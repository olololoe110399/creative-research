"""Check portable skill dependencies without installing anything or loading credentials."""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from run_cli import BridgeError, engine_python, preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--python", default=sys.executable)
    ns = parser.parse_args(argv)
    checks = [
        {"name": "bridge_python", "ok": sys.version_info >= (3, 11), "required": True},
        {
            "name": "uv",
            "ok": shutil.which("uv") is not None,
            "required": False,
            "detail": "Optional: needed only for checkout installation/development.",
        },
    ]
    try:
        version = preflight(engine_python(ns.python))["stdout"].strip()
        checks.append({"name": "engine", "ok": True, "required": True, "version": version})
    except (BridgeError, OSError) as exc:
        checks.append({"name": "engine", "ok": False, "required": True, "detail": str(exc)})
    ok = all(check["ok"] for check in checks if check["required"])
    print(json.dumps({"ok": ok, "checks": checks, "providers_called": False}))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
