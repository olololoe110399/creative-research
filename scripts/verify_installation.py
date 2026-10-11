"""Install wheel and sdist into fresh environments and exercise the offline contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

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
            accounts = isolated / "accounts.txt"
            accounts.write_text("synthetic_creator\n")
            run(
                cli + ["scrape", "--accounts-file", str(accounts), "--preflight"],
                cwd=isolated,
                env=env,
            )
            source = isolated / "crawl/posts"
            source.mkdir(parents=True)
            (source / "synthetic_creator.jsonl").write_text(
                json.dumps(
                    {
                        "id": "7649340799209065748",
                        "input": "synthetic_creator",
                        "text": "synthetic fixture",
                        "isSlideshow": False,
                        "webVideoUrl": "https://example.test/video/1",
                    }
                )
                + "\n"
            )
            media = isolated / "media/synthetic_creator/7649340799209065748"
            media.mkdir(parents=True)
            (media / "cover.jpg").write_bytes(b"synthetic-image")
            (media / "video.mp4").write_bytes(b"synthetic-video")
            export = isolated / "handoff"
            arguments = [
                "export-dataset",
                "--input",
                str(source.parent),
                "--media-root",
                str(media.parent.parent),
                "--out",
                str(export),
                "--zip",
            ]
            dry = json.loads(run(cli + arguments + ["--dry-run"], cwd=isolated, env=env))
            if not dry["dry_run"] or export.exists():
                raise RuntimeError("Installed export dry-run wrote files")
            report = json.loads(run(cli + arguments, cwd=isolated, env=env))
            if report["counts"]["posts"] != 1 or report["counts"]["missing_assets"]:
                raise RuntimeError("Installed export inventory failed")
            import zipfile

            with zipfile.ZipFile(report["zip"]) as archive:
                archive.extractall(isolated / "relocated")
            relocated = isolated / "relocated/handoff"
            import shutil

            shutil.rmtree(source.parent)
            shutil.rmtree(media.parent.parent)
            valid = json.loads(
                run(
                    cli + ["validate", "--dataset", str(relocated), "--json"], cwd=isolated, env=env
                )
            )
            if not valid["ok"]:
                raise RuntimeError("Relocated dataset depends on original sources")
            run(
                cli + ["validate", "--dataset", str(isolated / "missing"), "--json"],
                cwd=isolated,
                env=env,
                expected=1,
            )
            run(cli + arguments, cwd=isolated, env=env, expected=2)
            for retired in (
                "lab",
                "vision-videos",
                "intelligence-build",
                "production-kit",
                "prepare-media",
                "download-videos",
            ):
                run(cli + [retired], cwd=isolated, env=env, expected=2)
            # Exercise the installed orchestrator with synthetic providers only.
            pipeline_check = isolated / "check_pipeline.py"
            pipeline_check.write_text("""
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from creative_research.capture import media, scrape, videos
from creative_research.capture.pipeline import read_run
from creative_research.cli.app import execute
from pathlib import Path

calls = []
requests = []
post = {"id": "1", "input": "synthetic_creator", "webVideoUrl": "https://example.test/video/1",
        "videoMeta": {"originalCoverUrl": "https://example.test/cover"}, "isSlideshow": False}
class Client:
    def __init__(self, *args, **kwargs): pass
    def actor(self, name):
        def start(**kwargs):
            calls.append(kwargs)
            return {"id": "synthetic-run", "status": "RUNNING"}
        return SimpleNamespace(start=start)
    def run(self, run_id):
        return SimpleNamespace(wait_for_finish=lambda **kwargs:
            {"id": run_id, "status": "SUCCEEDED", "defaultDatasetId": "synthetic-dataset"})
    def dataset(self, dataset_id):
        return SimpleNamespace(iterate_items=lambda **kwargs: iter([post]))
actual_client = httpx.AsyncClient
def transport(request):
    requests.append(str(request.url))
    return httpx.Response(200, content=b"synthetic-image")
def image_client(**kwargs):
    return actual_client(transport=httpx.MockTransport(transport), **kwargs)
def video(url, out, browser, cookies):
    target = out / "video.mp4"
    target.write_bytes(b"synthetic-video")
    return target, None
with patch.dict("os.environ", {"APIFY_TOKEN": "synthetic-private-token"}), \\
     patch.object(scrape, "ApifyClient", Client), \\
     patch.object(media.httpx, "AsyncClient", image_client), \\
     patch.object(videos, "download_ytdlp", video), \\
     patch.object(videos, "ffprobe", lambda path: {}):
    assert execute(["run", "--accounts-file", "accounts.txt", "--out", "data/runs/synthetic", "--zip", "--json"]) == 0
    assert execute(["run", "--out", "data/runs/synthetic", "--resume", "--json"]) == 0
    assert len(calls) == 1 and len(requests) == 1
    state = read_run(Path("data/runs/synthetic"))
    assert state["complete"] and state["status"] == "completed"
    assert execute(["validate", "--dataset", state["dataset"], "--json"]) == 0
""")
            run([str(python), str(pipeline_check)], cwd=isolated, env=env)
            print(
                f"Fresh {kind} install: help, preflight, offline export, ZIP relocation, pipeline/resume and validation passed"
            )


if __name__ == "__main__":
    main()
