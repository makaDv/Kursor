"""Entry point for the frozen Windows executable (see packaging/windows/kursor.spec)."""

import sys

from kursor.desktop import main

if __name__ == "__main__":
    sys.exit(main())
