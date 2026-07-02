"""
Module 1: PDF Ingestor
=======================
Loads a PDF and produces per-page raw text (both layout-preserved and plain)
plus basic metadata. This is the single entry point every downstream module
(table locator, keyword search, chunker, etc.) builds on.

Design notes
------------
- Uses `pdfplumber` (pure Python, no poppler/pdftotext CLI dependency) in two
  modes per page:
    * page.extract_text(layout=True)  -> preserves column/whitespace
      alignment by placing each character according to its x/y position,
      similar to `pdftotext -layout`. Needed to locate tables.
    * page.extract_text()             -> normal reflowed text, better for
      keyword / full-text search.
- Results are cached to disk as JSON, keyed off the PDF's absolute path +
  mtime + size (so edits to the source PDF correctly invalidate the cache).
  Downstream modules rerun constantly during dev; re-parsing a 170-page PDF
  on every run is wasteful.

CLI usage
---------
    python pdf_ingestor.py path/to/file.pdf
    python pdf_ingestor.py path/to/file.pdf --no-cache
    python pdf_ingestor.py path/to/file.pdf --cache-dir /tmp/pdf_cache

Programmatic usage
-------------------
    from pdf_ingestor import ingest_pdf
    doc = ingest_pdf("Annual Report of Ombudsman Schemes, 2023-24.pdf")
    doc["num_pages"]
    doc["pages"][0]["text_layout"]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pdfplumber


DEFAULT_CACHE_DIR = Path.home() / ".cache" / "pdf_ingestor"


class PDFIngestError(RuntimeError):
    """Raised when the PDF can't be read or parsed."""


def _trim_blank_lines(text: str) -> str:
    """
    Strip leading/trailing whitespace-only lines.

    pdfplumber's layout=True mode pads output to the full page height with
    blank lines (one per unused text row), which is noisy but structurally
    meaningless. We trim only from the top/bottom, never touching interior
    lines, so column alignment inside the content is untouched.
    """
    lines = text.split("\n")
    start = 0
    end = len(lines)
    while start < end and lines[start].strip() == "":
        start += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    return "\n".join(lines[start:end])


def _cache_key(pdf_path: Path) -> str:
    """Stable cache key from absolute path + size + mtime, so edited PDFs invalidate cache."""
    stat = pdf_path.stat()
    raw = f"{pdf_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _cache_path(pdf_path: Path, cache_dir: Path) -> Path:
    return cache_dir / f"{pdf_path.stem}.{_cache_key(pdf_path)}.json"


def ingest_pdf(
    pdf_path: str | Path,
    use_cache: bool = True,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Load a PDF and return per-page text + metadata.

    Args:
        pdf_path: path to the PDF file.
        use_cache: if True, read/write a JSON cache on disk.
        cache_dir: directory to store cache files.
        force_refresh: if True, ignore any existing cache and re-extract.

    Returns:
        {
          "file_name": str,
          "num_pages": int,
          "pages": [
            {"page_num": int, "text_layout": str, "text_plain": str},
            ...
          ]
        }
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise PDFIngestError(f"File not found: {pdf_path}")
    if not pdf_path.is_file():
        raise PDFIngestError(f"Not a file: {pdf_path}")

    cache_dir = Path(cache_dir)
    cache_file: Optional[Path] = None

    if use_cache:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = _cache_path(pdf_path, cache_dir)
        if cache_file.exists() and not force_refresh:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                # Corrupt cache -- fall through and re-extract.
                pass

    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            num_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    text_layout = page.extract_text(layout=True) or ""
                except Exception as e:
                    raise PDFIngestError(
                        f"Failed to extract layout text from page {i} of {pdf_path}: {e}"
                    ) from e
                try:
                    text_plain = page.extract_text() or ""
                except Exception as e:
                    raise PDFIngestError(
                        f"Failed to extract plain text from page {i} of {pdf_path}: {e}"
                    ) from e
                pages.append(
                    {
                        "page_num": i,
                        "text_layout": _trim_blank_lines(text_layout),
                        "text_plain": _trim_blank_lines(text_plain),
                    }
                )
    except PDFIngestError:
        raise
    except Exception as e:
        raise PDFIngestError(f"Failed to open/parse {pdf_path}: {e}") from e

    doc = {
        "file_name": pdf_path.name,
        "num_pages": num_pages,
        "pages": pages,
    }

    if use_cache and cache_file is not None:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
        except OSError as e:
            # Cache write failure shouldn't break ingestion, just warn.
            print(f"Warning: failed to write cache to {cache_file}: {e}", file=sys.stderr)

    return doc


def _main() -> None:
    parser = argparse.ArgumentParser(description="Module 1: PDF Ingestor")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument(
        "--no-cache", action="store_true", help="Disable disk caching"
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore existing cache and re-extract",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help=f"Cache directory (default: {DEFAULT_CACHE_DIR})",
    )
    parser.add_argument(
        "-o", "--output", help="Write full JSON output to this file instead of stdout summary"
    )
    args = parser.parse_args()

    try:
        doc = ingest_pdf(
            args.pdf_path,
            use_cache=not args.no_cache,
            cache_dir=args.cache_dir,
            force_refresh=args.force_refresh,
        )
    except PDFIngestError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print(f"Wrote {doc['num_pages']} pages to {args.output}")
    else:
        print(f"file_name: {doc['file_name']}")
        print(f"num_pages: {doc['num_pages']}")
        if doc["pages"]:
            preview = doc["pages"][0]["text_plain"][:300]
            print("\n--- page 1 text_plain preview ---")
            print(preview)


if __name__ == "__main__":
    _main()
