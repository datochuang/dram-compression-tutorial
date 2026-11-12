#!/usr/bin/env python3
"""Run the reference models of the LZ4 hardware from anywhere: python3 sim/run_hwref.py --help"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwref.__main__ import main  # noqa: E402

if __name__ == '__main__':
    main()
