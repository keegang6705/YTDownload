#!/usr/bin/env python3
"""Backwards-compatible entry point.

The rich console output used to live in a separate ``YTDownload+.py`` file. It
is now the default for ``YTDownload.py`` (the old plain version is gone - two
copies of the same download logic is how bugs start). This shim stays so old
shortcuts and habits keep working.
"""

from YTDownload import main

if __name__ == "__main__":
    raise SystemExit(main())
