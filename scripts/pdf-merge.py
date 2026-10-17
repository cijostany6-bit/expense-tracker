#!/usr/bin/env python3
"""Merge PDFs losslessly with pypdf.

Unlike macOS PDFKit (which re-writes streams and bloats a 3 MB file to 29 MB),
pypdf copies page streams verbatim, so the result is the sum of the parts.

Usage:  pdf-merge.py <output.pdf> <input.pdf> [input.pdf ...]
"""
import sys


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print("usage: pdf-merge.py out.pdf in1.pdf [in2.pdf ...]", file=sys.stderr)
        return 2

    out, ins = args[0], args[1:]
    try:
        from pypdf import PdfWriter, PdfReader
    except Exception as exc:  # pragma: no cover - environment dependent
        print("pypdf unavailable: %s" % exc, file=sys.stderr)
        return 3

    writer = PdfWriter()
    total = 0
    for path in ins:
        try:
            reader = PdfReader(path)
            n = len(reader.pages)
            for page in reader.pages:
                writer.add_page(page)
            total += n
            print("  + %3d pages  %s" % (n, path.split("/")[-1]))
        except Exception as exc:  # pragma: no cover
            print("  ! skipped %s: %s" % (path, exc), file=sys.stderr)

    with open(out, "wb") as fh:
        writer.write(fh)
    print("  = %3d pages  -> %s" % (total, out.split("/")[-1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
