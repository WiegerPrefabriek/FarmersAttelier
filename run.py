#!/usr/bin/env python3
"""Start de Farmers Atelier Support-server.

    ./.venv/bin/python run.py            → http://127.0.0.1:8800/
    POORT=8801 ./.venv/bin/python run.py → andere poort
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.server import main  # noqa: E402

if __name__ == "__main__":
    main()
