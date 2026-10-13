"""Calls the native `avtbridge` helper, compiling it on first use.

The helper talks to macOS's private AvatarKit framework (see native/avtbridge.m).
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from functools import cache
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "native" / "avtbridge.m"
CACHE_DIR = Path.home() / "Library" / "Caches" / "avatarize"


class BridgeError(RuntimeError):
    pass


@cache
def macos_build() -> str:
    return subprocess.run(["sw_vers", "-buildVersion"], capture_output=True, text=True, check=True).stdout.strip()


@cache
def binary() -> Path:
    if platform.system() != "Darwin":
        raise BridgeError("Rendering needs macOS: it uses the AvatarKit framework that ships with it.")
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:12]
    exe = CACHE_DIR / f"avtbridge-{digest}"
    if not exe.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["clang", "-fobjc-arc", "-O2", "-framework", "Foundation", "-framework", "AppKit", str(SOURCE), "-o", str(exe)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise BridgeError(f"Could not compile avtbridge (are the Xcode command line tools installed?):\n{result.stderr}")
    return exe


def _run(*args: str) -> str:
    result = subprocess.run([str(binary()), *args], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise BridgeError(result.stderr.strip() or f"avtbridge {args[0]} failed")
    return result.stdout


@cache
def catalog() -> dict:
    """Every category with its valid preset ids and color names, cached per macOS build."""
    path = CACHE_DIR / f"catalog-{macos_build()}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = json.loads(_run("catalog"))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


@cache
def _neutral_json() -> str:
    return _run("neutral")


def neutral() -> dict:
    """A fresh copy of the neutral descriptor, safe to modify."""
    return json.loads(_neutral_json())


def normalize(descriptor_path: Path) -> dict:
    """The descriptor as AvatarKit actually loaded it (unknown ids are replaced silently)."""
    return json.loads(_run("normalize", str(descriptor_path)))


@cache
def poses() -> list[dict]:
    """Every sticker pose: [{"name", "pack", "label", "emoji"}], cached per macOS build."""
    path = CACHE_DIR / f"poses-{macos_build()}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = json.loads(_run("poses"))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def render(descriptor_path: Path, outputs: dict[str, Path], size: int = 512, margin: float = 0.04) -> None:
    """Renders one square PNG per pose: outputs maps pose name -> PNG path."""
    _run("render", str(descriptor_path), str(size), str(margin), *(f"{pose}={path}" for pose, path in outputs.items()))
