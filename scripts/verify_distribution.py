"""Verify exact release contents, version, license and private-file exclusions."""

from __future__ import annotations

import re
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

from creative_research import __version__

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT_FILES = {
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "LICENSE",
    "Makefile",
    "pyproject.toml",
    "uv.lock",
    ".env.example",
    ".gitignore",
    ".python-version",
}
SOURCE_EXTENSIONS = {
    "src": {".py", ".js", ".css", ".html", ".svg", ".typed"},
    "tests": {".py", ".cjs"},
    "scripts": {".py"},
    "docs": {".md"},
    "skills": {".md", ".py"},
}
CREDENTIAL_PATTERNS = {
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "Apify token": r"apify_api_[A-Za-z0-9]{20,}",
    "Google key": r"AIza[\w-]{30,}",
    "GitHub token": r"(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}",
    "AWS key": r"\bAKIA[A-Z0-9]{16}\b",
    "personal machine path": r"/(?:Users|home)/[A-Za-z0-9_.-]+/",
}


def audit_text(name: str, payload: bytes) -> None:
    """Pattern detection only: report location/category, never a matched secret."""
    value = payload.decode("utf-8")
    for category, pattern in CREDENTIAL_PATTERNS.items():
        match = re.search(pattern, value)
        if match:
            line = value.count("\n", 0, match.start()) + 1
            raise ValueError(f"Release review required: {name}:{line}: {category}")


def source_files(root: Path = ROOT) -> dict[str, Path]:
    metadata = tomllib.loads((root / "pyproject.toml").read_text())
    patterns = metadata["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    files = {}
    for pattern in patterns:
        matches = list(root.glob(pattern.lstrip("/")))
        if not matches:
            raise ValueError(f"Release input missing: {pattern}")
        for item in matches:
            paths = item.rglob("*") if item.is_dir() else [item]
            for path in paths:
                if not path.is_file():
                    continue
                name = path.relative_to(root).as_posix()
                top = name.split("/")[0]
                if (
                    top not in SOURCE_EXTENSIONS
                    and name not in PUBLIC_ROOT_FILES
                    and name != ".github/workflows/ci.yml"
                    and not (top == "config" and ".example." in path.name)
                ):
                    raise ValueError(f"Unexpected public release input: {name}")
                if top in SOURCE_EXTENSIONS and path.suffix not in SOURCE_EXTENSIONS[top]:
                    continue
                if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError(f"Release input must be a confined regular file: {name}")
                audit_text(name, path.read_bytes())
                files[name] = path
    if metadata["project"]["version"] != __version__:
        raise ValueError("Package metadata and CLI version differ")
    if metadata["project"]["license"] != "MIT" or "LICENSE" not in files:
        raise ValueError("Release requires the selected MIT license")
    return files


def check_metadata(payload: bytes) -> None:
    metadata = BytesParser().parsebytes(payload)
    if metadata["Name"] != "creative-research" or metadata["Version"] != __version__:
        raise ValueError("Distribution metadata differs from the release")
    if metadata["License-Expression"] != "MIT" or "LICENSE" not in metadata.get_all(
        "License-File", []
    ):
        raise ValueError("Distribution metadata is missing the MIT license")


def verify(root: Path = ROOT) -> tuple[Path, Path]:
    files = source_files(root)
    package_files = {
        name.removeprefix("src/"): source
        for name, source in files.items()
        if name.startswith("src/")
    }
    wheel = root / "dist" / f"creative_research-{__version__}-py3-none-any.whl"
    sdist = root / "dist" / f"creative_research-{__version__}.tar.gz"
    info = f"creative_research-{__version__}.dist-info"
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        expected = set(package_files) | {
            f"{info}/{name}"
            for name in ("METADATA", "WHEEL", "entry_points.txt", "RECORD", "licenses/LICENSE")
        }
        if len(names) != len(expected) or set(names) != expected:
            raise ValueError("Wheel file set differs from owned package sources and metadata")
        for name, source in package_files.items():
            if archive.read(name) != source.read_bytes():
                raise ValueError(f"Wheel source mismatch: {name}")
        check_metadata(archive.read(f"{info}/METADATA"))
        if archive.read(f"{info}/licenses/LICENSE") != files["LICENSE"].read_bytes():
            raise ValueError("Wheel license mismatch")
        entrypoints = archive.read(f"{info}/entry_points.txt").decode()
        if "creative-research = creative_research.cli.app:main" not in entrypoints:
            raise ValueError("Wheel CLI entry point missing")
    with tarfile.open(sdist) as archive:
        members = archive.getmembers()
        prefix = f"creative_research-{__version__}/"
        if any(not member.isfile() or not member.name.startswith(prefix) for member in members):
            raise ValueError("Source distribution contains unexpected paths or non-regular files")
        contents = {member.name.removeprefix(prefix): member for member in members}
        if len(contents) != len(members) or set(contents) != set(files) | {"PKG-INFO"}:
            raise ValueError("Source distribution file set differs from the public allowlist")
        for name, source in files.items():
            handle = archive.extractfile(contents[name])
            if handle is None or handle.read() != source.read_bytes():
                raise ValueError(f"Source distribution mismatch: {name}")
        metadata = archive.extractfile(contents["PKG-INFO"])
        if metadata is None:
            raise ValueError("Source distribution metadata missing")
        check_metadata(metadata.read())
    print(
        f"Release {__version__}: {len(package_files)} package files / {len(files)} public source files verified"
    )
    return wheel, sdist


if __name__ == "__main__":
    verify()
