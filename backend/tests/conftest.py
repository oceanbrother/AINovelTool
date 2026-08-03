# -*- coding: utf-8 -*-
"""Shared pytest fixtures and configuration for AINovelTool tests."""
import sys
from pathlib import Path

# Ensure the backend directory is on sys.path even when running pytest
# from a different directory.
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
