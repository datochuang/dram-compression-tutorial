#!/usr/bin/env python3
"""Run the host simulation of the kernel control procedures from anywhere: python3 sim/run_host.py --help"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hostsim.__main__ import main  # noqa: E402

if __name__ == '__main__':
    main()
