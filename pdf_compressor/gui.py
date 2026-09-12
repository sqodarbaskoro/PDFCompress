"""Provide the Tkinter interface and marshal worker results onto the UI thread."""

import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk

from pdf_compressor.compression import CompressionError, Mode, compress_pdf, validate_paths
from pdf_compressor.dependencies import find_ghostscript


class PdfCompressorApp:
    """Coordinate one compression job at a time without blocking Tkinter."""

    def __init__(self, root: tk.Tk) -> None:
        """Initialize interface state and arrange safe window closing."""
        self.root = root
        self.root.title("sy_pdf_compressor")
        self.root.geometry("760x470")
        self.root.minsize(700, 450)
        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=Mode.LOSSLESS.value)
        self.status_var = tk.StringVar(value="Select a PDF file to begin.")
        self.gs_cmd = find_ghostscript()
        self._busy = False
        self._results: Queue[tuple[bool, str]] = Queue()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self) -> None:
        """Build the familiar file selectors, mode selector, and status area."""
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        title = ttk.Label(
            main,
            text="Reduce PDF Size",
            font=("Segoe UI", 12, "bold"),
        )
        title.pack(anchor="w", pady=(0, 12))

        in_frame = ttk.Frame(main)
        in_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(in_frame, text="Input PDF:", width=14).pack(side="left")
        ttk.Entry(in_frame, textvariable=self.input_path_var).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(in_frame, text="Browse", command=self.select_input).pack(side="left")

        out_frame = ttk.Frame(main)
        out_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(out_frame, text="Output PDF:", width=14).pack(side="left")
        ttk.Entry(out_frame, textvariable=self.output_path_var).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(out_frame, text="Browse", command=self.select_output).pack(side="left")

        mode_frame = ttk.Frame(main)
        mode_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(mode_frame, text="Compression:", width=14).pack(side="left")
        mode_values = [mode.value for mode in Mode]
        mode_combo = ttk.Combobox(
            mode_frame,
            textvariable=self.mode_var,
            state="readonly",
            values=mode_values,
        )
        mode_combo.pack(side="left", fill="x", expand=True, padx=8)

        self.compress_btn = ttk.Button(
            main,
            text="Reduce PDF Size",
            command=self.start_compression,
        )
        self.compress_btn.pack(anchor="w", pady=(0, 12))

        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 10))

        note = ttk.Label(
            main,
            text=(
                "Lossless mode keeps original image/text quality.\n"
                "Balanced/Strong use Ghostscript and can reduce image quality."
            ),
            foreground="#444",
        )
        note.pack(anchor="w", pady=(0, 12))

        if not self.gs_cmd:
            self.status_var.set("Ghostscript not detected. Balanced/Strong require installation.")

        status = ttk.Label(main, textvariable=self.status_var, foreground="#0b4f8a")
        status.pack(anchor="w")

        ttk.Separator(main).pack(fill="x", pady=(16, 8))
        ttk.Label(
            main,
            text="Created by Sri Yanto Qodarbaskoro | Technical Support Engineer",
        ).pack(anchor="w")
        contacts = ttk.Frame(main)
        contacts.pack(anchor="w", pady=(4, 0))
        ttk.Button(
            contacts,
            text="sqodarbaskoro@gmail.com",
            command=self._open_email,
        ).pack(side="left")
        ttk.Button(
            contacts,
            text="LinkedIn",
            command=self._open_linkedin,
        ).pack(side="left", padx=(8, 0))

    def _open_email(self) -> None:
        """Open the creator's address in the user's default email application."""
        webbrowser.open("mailto:sqodarbaskoro@gmail.com")

    def _open_linkedin(self) -> None:
        """Open the creator's LinkedIn profile in the default browser."""
        webbrowser.open("https://www.linkedin.com/in/sqodarbaskoro/")

    def select_input(self) -> None:
        """Select an input and suggest an output filename."""
        path = filedialog.askopenfilename(
            title="Choose PDF file",
            filetypes=[("PDF files", "*.pdf")],
        )
        if not path:
            return

        self.input_path_var.set(path)
        input_path = Path(path)
        suggested_output = input_path.with_name(f"{input_path.stem}_reduced.pdf")

        if not self.output_path_var.get().strip():
            self.output_path_var.set(str(suggested_output))

        self.status_var.set("Input selected. Ready to optimize.")

    def select_output(self) -> None:
        """Choose a destination without writing to it."""
        path = filedialog.asksaveasfilename(
            title="Save optimized PDF as",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
        )
        if path:
            self.output_path_var.set(path)

    def start_compression(self) -> None:
        """Snapshot and validate UI values before starting a background job."""
        if self._busy:
            return
        try:
            source, destination = validate_paths(
                self.input_path_var.get().strip(), self.output_path_var.get().strip()
            )
            mode = Mode(self.mode_var.get())
        except (CompressionError, ValueError, OSError) as exc:
            messagebox.showerror("Invalid request", str(exc))
            return
        self._busy = True
        self.compress_btn.config(state="disabled")
        # Neither engine exposes reliable percentage progress. Show activity only.
        self.progress.start(15)
        self.status_var.set("Compressing PDF... please wait.")
        threading.Thread(
            target=self._run_compression, args=(source, destination, mode), daemon=False
        ).start()
        self.root.after(100, self._poll_results)

    def _run_compression(self, source: Path, destination: Path, mode: Mode) -> None:
        """Send plain result data through a queue without calling any Tk API."""
        try:
            result = compress_pdf(source, destination, mode)
            self._results.put((True, result.message))
        except Exception as exc:
            # Convert now: exception variables are cleared when the except ends.
            self._results.put((False, str(exc)))

    def _poll_results(self) -> None:
        """Consume worker messages exclusively from the Tkinter event loop."""
        try:
            success, message = self._results.get_nowait()
        except Empty:
            self.root.after(100, self._poll_results)
            return
        self._busy = False
        self.progress.stop()
        self.compress_btn.config(state="normal")
        self.status_var.set(message if success else "Compression failed.")
        if success:
            messagebox.showinfo("Compression complete", message)
        else:
            messagebox.showerror("Compression failed", message)

    def _close(self) -> None:
        """Keep the event loop alive until the worker has cleaned up its files."""
        if self._busy:
            messagebox.showinfo(
                "Compression running", "Wait for compression to finish before closing."
            )
            return
        self.root.destroy()


def main() -> None:
    """Launch the desktop application."""
    root = tk.Tk()
    PdfCompressorApp(root)
    root.mainloop()
