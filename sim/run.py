#!/usr/bin/env python3
"""Run the simulator from anywhere: python3 sim/run.py --help"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lz4sim.__main__ import main  # noqa: E402

if __name__ == '__main__':
    main()
