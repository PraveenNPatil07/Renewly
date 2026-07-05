"""
conftest.py — pytest configuration.

Adds the renewly/ directory to sys.path so all module imports resolve
correctly when running `pytest` from within the renewly/ directory.
"""
import sys
import os

# Ensure the project root (renewly/) is on sys.path
sys.path.insert(0, os.path.dirname(__file__))
