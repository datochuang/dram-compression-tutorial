"""LZ4 DRAM compression system simulator."""
from .config import SystemConfig, SMALL
from .sim import Simulation, format_report

__all__ = ['SystemConfig', 'SMALL', 'Simulation', 'format_report']
