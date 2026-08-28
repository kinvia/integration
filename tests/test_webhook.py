"""Tests for webhook health path constants."""

import importlib.util
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "kinvia"
if "kinvia" not in sys.modules:
    pkg = types.ModuleType("kinvia")
    pkg.__path__ = [str(PKG_DIR)]
    sys.modules["kinvia"] = pkg
spec = importlib.util.spec_from_file_location("kinvia.const", PKG_DIR / "const.py")
const = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(const)


def test_health_paths_defined():
    assert const.SERVER_HEALTH_PATH == "/health"
    assert const.WEBHOOK_HEALTH_PATH == "/api/v1/webhooks/health"
