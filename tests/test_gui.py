"""Check worker isolation without creating windows or requiring a display."""

import threading
from pathlib import Path
from queue import Queue

import pytest

from pdf_compressor import gui
from pdf_compressor.compression import CompressionError, CompressionResult, Mode


@pytest.mark.parametrize("fails", [False, True])
def test_worker_queues_plain_data(monkeypatch: pytest.MonkeyPatch, fails: bool) -> None:
    """Ensure delayed failure reporting needs no Tk methods or live exception."""
    app = gui.PdfCompressorApp.__new__(gui.PdfCompressorApp)
    app._results = Queue()

    def compress(*args: object) -> CompressionResult:
        """Return a result or raise an exception that expires before consumption."""
        if fails:
            raise CompressionError("synthetic failure")
        return CompressionResult(Path("output.pdf"), 100, 125)

    monkeypatch.setattr(gui, "compress_pdf", compress)
    worker = threading.Thread(
        target=app._run_compression,
        args=(Path("input.pdf"), Path("output.pdf"), Mode.LOSSLESS),
    )
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    success, message = app._results.get(timeout=1)
    assert success is not fails
    assert "synthetic failure" in message if fails else "Larger" in message
