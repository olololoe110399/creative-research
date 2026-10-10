"""Install wheel and sdist into fresh environments and exercise the offline contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from install_agent_skill import install as install_skill
from verify_distribution import ROOT, verify

from creative_research import __version__
from creative_research.cli.registry import COMMAND_SPECS


def run(args: list[str], *, cwd: Path, env: dict[str, str], expected: int = 0) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, timeout=300)
    if result.returncode != expected:
        raise RuntimeError(
            f"Release check failed ({result.returncode}, expected {expected}): {' '.join(args)}\n"
            f"{result.stdout[-3000:]}\n{result.stderr[-3000:]}"
        )
    return result.stdout


def main() -> None:
    artifacts = verify()
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("CREATIVE_RESEARCH_")
        and key not in {"PYTHONPATH", "VIRTUAL_ENV", "APIFY_TOKEN", "GEMINI_API_KEY"}
    }
    env["NO_COLOR"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="creative-research-release-") as temporary:
        directory = Path(temporary).resolve()
        requirements = directory / "requirements.txt"
        run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--no-header",
                "--no-annotate",
                "--output-file",
                str(requirements),
            ],
            cwd=ROOT,
            env=env,
        )
        for artifact in artifacts:
            kind = "wheel" if artifact.suffix == ".whl" else "sdist"
            isolated = directory / kind
            isolated.mkdir()
            venv = isolated / "venv"
            run(["uv", "venv", "--python", sys.executable, str(venv)], cwd=isolated, env=env)
            python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            run(
                [
                    "uv",
                    "pip",
                    "sync",
                    "--python",
                    str(python),
                    "--require-hashes",
                    str(requirements),
                ],
                cwd=isolated,
                env=env,
            )
            run(
                ["uv", "pip", "install", "--python", str(python), "--no-deps", str(artifact)],
                cwd=isolated,
                env=env,
            )
            run(["uv", "pip", "check", "--python", str(python)], cwd=isolated, env=env)
            installed = Path(
                run(
                    [
                        str(python),
                        "-c",
                        "import creative_research; print(creative_research.__file__)",
                    ],
                    cwd=isolated,
                    env=env,
                ).strip()
            )
            if not installed.is_relative_to(venv):
                raise RuntimeError(f"Release check imported an unexpected package: {installed}")
            binary = venv / (
                "Scripts/creative-research.exe" if os.name == "nt" else "bin/creative-research"
            )
            cli = [str(binary)]
            if run(cli + ["--version"], cwd=isolated, env=env).strip() != __version__:
                raise RuntimeError("Installed CLI version mismatch")
            run(cli + ["--help"], cwd=isolated, env=env)
            module_cli = [str(python), "-m", "creative_research"]
            if run(module_cli + ["--version"], cwd=isolated, env=env).strip() != __version__:
                raise RuntimeError("Installed module entry point version mismatch")
            run(module_cli + ["--help"], cwd=isolated, env=env)
            for spec in COMMAND_SPECS:
                run(cli + [spec.name, "--help"], cwd=isolated, env=env)
            run(cli + ["unknown-command"], cwd=isolated, env=env, expected=2)
            blocked = json.loads(
                run(
                    cli + ["intelligence-build", "--dry-run", "--json"],
                    cwd=isolated,
                    env=env,
                )
            )
            if blocked["status"] != "blocked":
                raise RuntimeError("Empty workspace should report blocked inputs")
            demo = isolated / "demo"
            report = json.loads(
                run(cli + ["demo", "--out", str(demo), "--json"], cwd=isolated, env=env)
            )
            if report["status"] != "complete" or len(report["stages"]) != 12:
                raise RuntimeError("Installed package offline demo failed")
            run(cli + ["--root", str(demo), "validate", "--json"], cwd=isolated, env=env)
            hosts = isolated / "agent-project"
            hosts.mkdir()
            for skill in install_skill(
                ROOT / "skills/creative-research", hosts, ["claude", "codex"]
            ):
                doctor = json.loads(
                    run([str(python), str(skill / "scripts/doctor.py")], cwd=hosts, env=env)
                )
                if not doctor["ok"] or doctor["providers_called"]:
                    raise RuntimeError("Installed portable skill dependency check failed")
                bridge = [str(python), str(skill / "scripts/run_cli.py"), "--root", str(demo)]
                for arguments in (
                    ["status"],
                    ["validate"],
                    ["rank-posts", "--top", "2"],
                    [
                        "query",
                        "data/06_analytics/post_performance.parquet",
                        "--columns",
                        "post_uid,views",
                        "--limit",
                        "2",
                    ],
                    ["intelligence-build"],
                ):
                    response = json.loads(run(bridge + arguments, cwd=hosts, env=env))
                    if response["exit_code"] or response["truncated"]:
                        raise RuntimeError("Fresh portable skill bridge failed")
            rerun = json.loads(
                run(
                    cli + ["--root", str(demo), "intelligence-build", "--json"],
                    cwd=isolated,
                    env=env,
                )
            )
            if rerun["status"] != "complete" or not all(
                s["status"] == "reused" for s in rerun["stages"]
            ):
                raise RuntimeError("Installed package did not reuse fresh stages")
            run(cli + ["demo", "--out", str(demo)], cwd=isolated, env=env, expected=2)
            master = "data/05_master/creative_master.parquet"
            for args in (
                ["status", "--json"],
                ["calibrate-families", "--progress-every", "0"],
                ["preview-families-v2"],
                ["judge-family-candidates", "--dry-run"],
                ["rank-posts", master, "--top", "3", "--out", "ranked.csv"],
                [
                    "query",
                    master,
                    "--where",
                    "views>=1000",
                    "--columns",
                    "account,post_id",
                    "--out",
                    "filtered.csv",
                ],
                [
                    "extract-references",
                    master,
                    "--out",
                    "references",
                    "--media",
                    "none",
                    "--top",
                    "3",
                ],
                ["group-references", "references/references.parquet"],
                ["review-knowledge", "queue"],
                ["production-kit"],
            ):
                run(cli + ["--root", str(demo)] + args, cwd=isolated, env=env)
            for name in (
                "ranked.csv",
                "filtered.csv",
                "references/references.parquet",
                "references/index.html",
                "references/candidate_groups.csv",
            ):
                if not (demo / name).is_file():
                    raise RuntimeError(f"Installed CLI did not produce {name}")
            print(
                f"Fresh {kind} install: all command help, failure paths, 12-stage demo, reuse and offline utilities passed"
            )


if __name__ == "__main__":
    main()
