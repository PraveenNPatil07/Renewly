"""
config.py — Top-level configuration.

Reads environment variables and provides the active MemoryPort adapter
to the rest of the application. This is the only file that application
startup code needs to import from — it delegates the actual adapter
selection to memory/factory.py.
"""

from memory.factory import get_memory_adapter
from memory.port import MemoryPort

__all__ = ["get_memory_adapter", "MemoryPort"]
