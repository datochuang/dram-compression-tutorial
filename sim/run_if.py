#!/usr/bin/env python3
"""Run the HW/FW interface simulator from anywhere: python3 sim/run_if.py --help"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ifsim.__main__ import main  # noqa: E402

if __name__ == '__main__':
    main()
