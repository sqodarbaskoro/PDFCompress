"""Validate requests and compress PDFs without touching interface state."""

import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType

from pdf_compressor.dependencies import find_ghostscript


class CompressionError(Exception):
    """Describe a compression failure suitable for display to the user."""


class Mode(str, Enum):
    """Expose the three supported compression strategies."""

    LOSSLESS = "Lossless (original quality)"
    BALANCED = "Balanced (high quality, smaller size)"
    STRONG = "Strong (higher compression, lower quality)"


@dataclass(frozen=True)
class CompressionResult:
    """Record actual file sizes, including results that grew."""

    output: Path
    before_bytes: int
    after_bytes: int

    @property
    def message(self) -> str:
        """Describe the size change without implying every PDF gets smaller."""
        change = self.after_bytes - self.before_bytes
        percentage = abs(change) / self.before_bytes * 100 if self.before_bytes else 0
        outcome = (
            f"Larger by {percentage:.2f}%"
            if change > 0
            else f"Saved {percentage:.2f}%"
            if change < 0
            else "Size unchanged"
        )
        return (
            f"Original: {self.before_bytes:,} bytes | "
            f"Output: {self.after_bytes:,} bytes | {outcome}"
        )


def validate_paths(source: str | Path, destination: str | Path) -> tuple[Path, Path]:
    """Reject missing paths, input aliases, and existing output destinations."""
    if not str(source).strip() or not str(destination).strip():
        raise CompressionError("Choose both an input PDF and an output file path.")
    source = Path(source).expanduser().absolute()
    destination = Path(destination).expanduser().absolute()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise CompressionError("Input must be an existing PDF file.")
    if destination.suffix.lower() != ".pdf":
        raise CompressionError("Output must have a .pdf extension.")
    if source.resolve() == destination.resolve() or (
        destination.exists() and source.samefile(destination)
    ):
        raise CompressionError("Input and output files must be different.")
    if os.path.lexists(destination):
        raise CompressionError("Output already exists. Choose a new filename.")
    if not destination.parent.is_dir():
        raise CompressionError("The output folder does not exist.")
    return source, destination


def _load_pikepdf() -> ModuleType:
    """Load pikepdf only when needed and explain installation failures."""
    try:
        import pikepdf
    except ImportError as exc:
        raise CompressionError("pikepdf is required. Install with: pip install .") from exc
    return pikepdf


def _lossless(source: Path, destination: Path) -> None:
    """Rewrite streams and objects without resampling images."""
    pikepdf = _load_pikepdf()
    with pikepdf.Pdf.open(source) as pdf:
        if pdf.is_encrypted:
            raise CompressionError("Encrypted PDFs are not supported. Unlock a copy first.")
        # Linearization adds web-viewing overhead and is unnecessary for local files.
        pdf.save(
            destination,
            compress_streams=True,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
        )


def _ghostscript(source: Path, destination: Path, mode: Mode) -> None:
    """Run pdfwrite with bounded execution and readable failure diagnostics."""
    executable = find_ghostscript()
    if executable is None:
        raise CompressionError("Ghostscript is required for Balanced and Strong modes.")
    preset, dpi, mono_dpi = ("/ebook", 170, 300) if mode is Mode.BALANCED else ("/screen", 120, 220)
    # Explicit resolutions retain the original app's tradeoffs. Presets also
    # affect fonts and image encoding; they do not guarantee a target file size.
    command = [
        executable,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.6",
        "-dSAFER",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        f"-dPDFSETTINGS={preset}",
        "-dAutoRotatePages=/None",
    ]
    for kind, resolution, method in (
        ("Color", dpi, "Bicubic"),
        ("Gray", dpi, "Bicubic"),
        ("Mono", mono_dpi, "Subsample"),
    ):
        command.extend(
            [
                f"-dDownsample{kind}Images=true",
                f"-d{kind}ImageDownsampleType=/{method}",
                f"-d{kind}ImageResolution={resolution}",
            ]
        )
    command.extend([f"-sOutputFile={destination}", "-f", str(source)])
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise CompressionError("Ghostscript exceeded the 10-minute time limit.") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or b"").decode(errors="replace")[-2000:]
        raise CompressionError(
            f"Ghostscript failed (exit {exc.returncode}). {details.strip()}"
        ) from exc
    except OSError as exc:
        raise CompressionError(f"Could not start Ghostscript: {exc}") from exc


def compress_pdf(
    source: str | Path,
    destination: str | Path,
    mode: Mode = Mode.LOSSLESS,
) -> CompressionResult:
    """Publish a complete PDF exclusively, preserving input and existing outputs."""
    try:
        mode = Mode(mode)
        source, destination = validate_paths(source, destination)
        pikepdf = _load_pikepdf()
        before_bytes = source.stat().st_size
        with pikepdf.Pdf.open(source) as pdf:
            if pdf.is_encrypted:
                raise CompressionError("Encrypted PDFs are not supported. Unlock a copy first.")
            page_count = len(pdf.pages)
        # Same-folder staging supports an atomic hard-link publication. Unique
        # directories prevent concurrent jobs colliding and clean up on failure.
        with TemporaryDirectory(prefix=".pdf-compressor-", dir=destination.parent) as temp:
            staged = Path(temp) / "compressed.pdf"
            if mode is Mode.LOSSLESS:
                _lossless(source, staged)
            else:
                intermediate = Path(temp) / "ghostscript.pdf"
                _ghostscript(source, intermediate, mode)
                _lossless(intermediate, staged)
                # The second pass is optional optimization, so keep the smaller PDF.
                if intermediate.stat().st_size < staged.stat().st_size:
                    staged = intermediate
            with pikepdf.Pdf.open(staged) as pdf:
                if len(pdf.pages) != page_count:
                    raise CompressionError("Compression changed the page count.")
            after_bytes = staged.stat().st_size
            # link() fails if another process creates the destination after
            # validation. Never fall back to a write that could overwrite it.
            os.link(staged, destination)
        return CompressionResult(destination, before_bytes, after_bytes)
    except CompressionError:
        raise
    except Exception as exc:
        raise CompressionError(f"Compression failed: {exc}") from exc
