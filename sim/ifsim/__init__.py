"""HW/FW interface simulator for the SW-leaning LZ4 DRAM compression design.

Transaction level, discrete event, not cycle based. The interface (registers,
rings, structures, rules) is defined once in interface.json; the FW model, the
HW model, the checkers and the generated spec all read that file.
"""
