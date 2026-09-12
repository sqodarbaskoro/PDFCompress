"""Test discovery without depending on the host's installed executables."""

from pathlib import Path

import pytest

from pdf_compressor import dependencies


def test_path_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prefer the console executable explicitly available on PATH."""
    monkeypatch.setattr(
        dependencies.shutil, "which", lambda name: "/tools/gs" if name == "gs" else None
    )
    assert dependencies.find_ghostscript() == "/tools/gs"


def test_missing_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return no result when neither PATH nor fallback files provide an engine."""
    monkeypatch.setattr(dependencies.shutil, "which", lambda name: None)
    monkeypatch.setattr(dependencies.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(Path, "is_file", lambda path: False)
    assert dependencies.find_ghostscript() is None
