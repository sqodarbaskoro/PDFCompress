# sy_pdf_compressor

A small Python desktop application for compressing PDFs locally with a familiar Tkinter interface. Choose an input, select one of three compression modes, and save to a new PDF. No upload service or account is involved.

## Creator

Created by **Sri Yanto Qodarbaskoro**, Technical Support Engineer.

Contact: [sqodarbaskoro@gmail.com](mailto:sqodarbaskoro@gmail.com) | [LinkedIn](https://www.linkedin.com/in/sqodarbaskoro/)

## Compression modes

| Mode | Engine | Tradeoff |
| --- | --- | --- |
| Lossless | pikepdf | Recompresses streams and packs objects without resampling images. Already optimized PDFs may barely change or grow. |
| Balanced | Ghostscript, then pikepdf | Uses the ebook preset with color/grayscale resolution set to 170 DPI and monochrome to 300 DPI. Images may lose detail. |
| Strong | Ghostscript, then pikepdf | Uses the screen preset with color/grayscale resolution set to 120 DPI and monochrome to 220 DPI. Greater potential image quality loss. |

Resolutions are engine settings, not guarantees that every image is resampled. For Ghostscript modes, the smaller of the engine output and its subsequent lossless rewrite is retained. Every mode reports actual byte sizes and explicitly reports growth. A larger result is still saved so you can inspect it.

## Setup and launch

Python 3.11 through 3.14 are the supported target versions. Create a virtual environment from the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m pdf_compressor
```

On Windows, use `py -m venv .venv` and `.venv\Scripts\Activate.ps1` in PowerShell. After installation, `sy_pdf_compressor` also launches the app. From the source directory, you can also run `python sy_pdf_compressor.py`. `python -m pip install -r requirements.txt` installs the same project dependencies.

Tkinter is supplied by your Python distribution or operating system, not pip. Verify it with `python -m tkinter`. If missing, install a Python distribution with Tk support or your distribution's matching Tkinter package (commonly `python3-tk` on Debian/Ubuntu). Some macOS Python installations need a matching Tcl/Tk package.

Balanced and Strong additionally need [Ghostscript](https://ghostscript.com/releases/gsdnld.html). Install its console executable and put it on PATH (`gs` on macOS/Linux, `gswin64c` or `gswin32c` on Windows). Discovery also checks common installation directories. Lossless works without Ghostscript. Missing dependencies produce an error; the app does not silently change modes. All modes require pikepdf.

## Safety and limitations

- Choose a new output filename. Existing outputs, symlinks, and input aliases are rejected. Originals are never intentionally rewritten.
- Work is staged in unique temporary directories beside the destination and cleaned up on normal success or failure. Final publication uses a hard link to avoid overwriting a concurrently created file. The destination filesystem must support hard links; unsupported filesystems fail without a fallback overwrite.
- Engine work runs in a background thread. The main thread polls a result queue and shows an activity bar, not a measured completion percentage. Closing is blocked while a job runs. There is no cancellation, and Ghostscript has a ten-minute timeout. The pikepdf pass has no timeout.
- Encrypted PDFs are unsupported, including PDFs that open without a user password. Unlock a separate copy first.
- Lossless refers to image/text quality, not byte identity or preservation of every PDF feature. Rewriting can invalidate digital signatures. Ghostscript reconstructs a document and may change interactive features, metadata, fonts, colors, or accessibility information. Inspect important outputs before using them.
- Successful outputs are reopened and checked for page-count consistency. This does not establish visual fidelity or preservation of forms, annotations, attachments, or PDF/A compliance.
- Compression depends on document contents. There is no target-size option or guaranteed reduction. No quality benchmarks are claimed.
- Abrupt process termination or power loss can leave `.pdf-compressor-*` directories. Remove these only when no compression job is running. Do not modify the source externally during a job.

See the [pikepdf optimization notes](https://pikepdf.readthedocs.io/en/latest/topics/stream.html) and [Ghostscript high-level device documentation](https://ghostscript.readthedocs.io/en/latest/VectorDevices.html) for engine behavior and tradeoffs.

## Development

```sh
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest
```

Tests generate their own PDFs and cover validation, actual lossless rewriting, encrypted/malformed documents, missing dependencies, subprocess failures, temporary cleanup, overwrite races, and size reporting. Ghostscript integration tests skip if the executable is absent. CI installs Ghostscript and runs checks on Linux with Python 3.11 through 3.14. The workflow is configured but must run on GitHub before its results can be claimed.

The project separates responsibilities without a framework:

```text
pdf_compressor/
    compression.py   # Validation, engine execution, safe output publication
    dependencies.py  # Ghostscript discovery
    gui.py           # Tkinter widgets and worker coordination
    __main__.py      # Module launcher
sy_pdf_compressor.py   # Script launcher
tests/               # Synthetic-document tests
```

macOS, Windows, and Linux compatibility is intended. Local verification details are recorded below; a CI configuration is not evidence of successful runs on other platforms. Native desktop behavior still needs manual testing on each platform.

## Preparing a public repository

All PDF files are ignored deliberately, including personal originals and compressed copies. Personal documents are not included in the project; tests generate synthetic PDFs. `.vscode/` is ignored to keep personal editor and environment settings out of the repository. Caches, environments, build artifacts, and temporary directories are also ignored. Do not force-add private documents or publish an unfiltered archive of this folder. If PDFs were ever committed elsewhere, ignoring them does not remove that history.

MIT is a suitable permissive license for this small application. Before adding it, the owner should confirm the copyright holder name and copyright year, and approve that license choice. No license has been added yet, so the project does not currently grant an open-source license. Dependencies retain their own licenses; review those separately if distributing bundled engines or binaries.

Local verification: macOS 26.6.2 on Apple Silicon, Python 3.14.7, pikepdf 10.13.0.post1, Ghostscript 10.08.0, and Tk 9.0. All 27 automated tests passed, as did Ruff lint/format checks, dependency consistency checks, and a Tkinter construction/close smoke test. Full interactive desktop testing remains pending. Automated engine tests ran locally; Windows and Linux have not been tested locally.
