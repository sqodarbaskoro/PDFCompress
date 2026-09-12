"""Exercise compression and failures using disposable synthetic PDFs."""

import subprocess
from pathlib import Path

import pikepdf
import pytest

from pdf_compressor import compression
from pdf_compressor.compression import CompressionError, CompressionResult, Mode, compress_pdf
from pdf_compressor.dependencies import find_ghostscript


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """Generate a valid one-page PDF without using personal documents."""
    path = tmp_path / "input.pdf"
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(200, 200))
        page.Contents = pdf.make_stream(b"0.2 0.4 0.8 rg 20 20 100 100 re f\n" * 100)
        pdf.save(path)
    return path


def test_lossless_preserves_input(source: Path) -> None:
    """Verify a real rewrite is readable and leaves the source byte-identical."""
    original = source.read_bytes()
    output = source.with_name("output.pdf")
    result = compress_pdf(source, output)
    assert source.read_bytes() == original
    assert result.after_bytes == output.stat().st_size
    with pikepdf.Pdf.open(output) as pdf:
        assert len(pdf.pages) == 1
    assert not list(source.parent.glob(".pdf-compressor-*"))


@pytest.mark.parametrize("destination", ["", "   ", "output.txt", "missing/output.pdf"])
def test_invalid_destination(
    source: Path, destination: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject empty destinations and invalid extensions or parent folders."""
    monkeypatch.chdir(source.parent)
    with pytest.raises(CompressionError):
        compress_pdf(source, destination)


def test_input_alias_and_overwrite(source: Path) -> None:
    """Protect input aliases and existing output bytes."""
    alias = source.with_name("alias.pdf")
    alias.hardlink_to(source)
    for destination in (source, alias):
        with pytest.raises(CompressionError, match="different"):
            compress_pdf(source, destination)
    output = source.with_name("existing.pdf")
    output.write_bytes(b"keep me")
    with pytest.raises(CompressionError, match="already exists"):
        compress_pdf(source, output)
    assert output.read_bytes() == b"keep me"


def test_invalid_pdf(tmp_path: Path) -> None:
    """Reject malformed input without leaving an output behind."""
    source = tmp_path / "invalid.pdf"
    source.write_bytes(b"not a PDF")
    output = tmp_path / "output.pdf"
    with pytest.raises(CompressionError):
        compress_pdf(source, output)
    assert not output.exists()


def test_encrypted_pdf(source: Path) -> None:
    """Reject encryption instead of silently removing access restrictions."""
    encrypted = source.with_name("encrypted.pdf")
    with pikepdf.Pdf.open(source) as pdf:
        pdf.save(encrypted, encryption=pikepdf.Encryption(owner="owner", user=""))
    with pytest.raises(CompressionError, match="Encrypted"):
        compress_pdf(encrypted, source.with_name("output.pdf"))


def test_missing_pikepdf(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Give actionable feedback when the Python dependency is absent."""
    import sys

    monkeypatch.setitem(sys.modules, "pikepdf", None)
    with pytest.raises(CompressionError, match="pikepdf is required"):
        compress_pdf(source, source.with_name("output.pdf"))


def test_missing_ghostscript(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail explicitly instead of silently changing the chosen mode."""
    monkeypatch.setattr(compression, "find_ghostscript", lambda: None)
    with pytest.raises(CompressionError, match="Ghostscript is required"):
        compress_pdf(source, source.with_name("output.pdf"), Mode.BALANCED)
    assert not list(source.parent.glob(".pdf-compressor-*"))


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CalledProcessError(1, "gs", stderr=b"synthetic engine failure"),
        subprocess.TimeoutExpired("gs", 600),
        OSError("cannot execute"),
    ],
)
def test_subprocess_failure(
    source: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """Clean partial engine output on process errors and timeouts."""

    def fail(command: list[str], **kwargs: object) -> None:
        """Simulate an engine writing a partial file before failing."""
        output = next(arg.split("=", 1)[1] for arg in command if arg.startswith("-sOutputFile="))
        Path(output).write_bytes(b"partial")
        raise failure

    monkeypatch.setattr(compression, "find_ghostscript", lambda: "gs")
    monkeypatch.setattr(compression.subprocess, "run", fail)
    output = source.with_name("output.pdf")
    with pytest.raises(CompressionError, match="Ghostscript"):
        compress_pdf(source, output, Mode.STRONG)
    assert not output.exists()
    assert not list(source.parent.glob(".pdf-compressor-*"))


def test_destination_race(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Preserve a destination created after initial validation."""
    output = source.with_name("output.pdf")
    original = compression._lossless

    def competing_write(source: Path, staged: Path) -> None:
        """Create a competing destination while the staged PDF is being written."""
        original(source, staged)
        output.write_bytes(b"another job")

    monkeypatch.setattr(compression, "_lossless", competing_write)
    with pytest.raises(CompressionError):
        compress_pdf(source, output)
    assert output.read_bytes() == b"another job"
    assert not list(source.parent.glob(".pdf-compressor-*"))


def test_larger_result() -> None:
    """Report growth instead of hiding it behind zero savings."""
    result = CompressionResult(Path("output.pdf"), 100, 125)
    assert "Larger by 25.00%" in result.message


@pytest.mark.integration
@pytest.mark.parametrize("mode", [Mode.BALANCED, Mode.STRONG])
def test_real_ghostscript(source: Path, mode: Mode) -> None:
    """Exercise both presets with the installed engine when available."""
    if find_ghostscript() is None:
        pytest.skip("Ghostscript is not installed")
    original = source.read_bytes()
    output = source.with_name("output.pdf")
    compress_pdf(source, output, mode)
    with pikepdf.Pdf.open(output) as pdf:
        assert len(pdf.pages) == 1
    assert source.read_bytes() == original


@pytest.mark.parametrize("failure_kind", ["partial", "invalid", "publish"])
def test_staging_failure(source: Path, monkeypatch: pytest.MonkeyPatch, failure_kind: str) -> None:
    """Keep failures in private staging, including unsupported hard-link publication."""
    output = source.with_name("output.pdf")

    def broken_pass(source: Path, staged: Path) -> None:
        """Write incomplete bytes, optionally simulating a disk error."""
        staged.write_bytes(b"invalid PDF")
        if failure_kind == "partial":
            raise OSError("disk full")

    def broken_link(*args: object) -> None:
        """Simulate a filesystem that cannot publish using hard links."""
        raise OSError("hard links unsupported")

    if failure_kind == "publish":
        monkeypatch.setattr(compression.os, "link", broken_link)
    else:
        monkeypatch.setattr(compression, "_lossless", broken_pass)
    with pytest.raises(CompressionError):
        compress_pdf(source, output)
    assert not output.exists()
    assert not list(source.parent.glob(".pdf-compressor-*"))


@pytest.mark.parametrize("input_name", ["", "missing.pdf", "."])
def test_invalid_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, input_name: str) -> None:
    """Reject absent inputs and directories before invoking an engine."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CompressionError):
        compress_pdf(input_name, tmp_path / "output.pdf")
