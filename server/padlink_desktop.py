"""Entry point for the frozen Windows executable (see packaging/windows/padlink.spec)."""

import sys

from padlink.desktop import main

if __name__ == "__main__":
    sys.exit(main())
