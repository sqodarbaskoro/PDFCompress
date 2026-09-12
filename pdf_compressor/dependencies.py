"""Discover optional system tools without importing the interface."""

import os
import platform
import shutil
from pathlib import Path


def find_ghostscript() -> str | None:
    """Find a Ghostscript console executable on PATH or in common locations."""
    for name in ("gs", "gswin64c", "gswin32c"):
        if executable := shutil.which(name):
            return executable

    # GUI launches sometimes inherit a smaller PATH than terminal sessions.
    system = platform.system()
    candidates: list[Path] = []
    if system == "Darwin":
        candidates = [
            Path(p) / "gs" for p in ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin")
        ]
    elif system == "Windows":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            base = Path(os.environ.get(variable, "C:/Program Files")) / "gs"
            candidates.extend(sorted(base.glob("gs*/bin/gswin*c.exe"), reverse=True))
    else:
        candidates = [Path("/usr/bin/gs"), Path("/usr/local/bin/gs")]
    return next(
        (str(path) for path in candidates if path.is_file() and os.access(path, os.X_OK)),
        None,
    )
