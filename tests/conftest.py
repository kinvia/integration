"""Test fixtures that load kinvia modules without Home Assistant."""

import importlib.util
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "kinvia"


def _load_submodule(name: str):
    full_name = f"kinvia.{name}"
    if "kinvia" not in sys.modules:
        pkg = types.ModuleType("kinvia")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["kinvia"] = pkg
    path = PKG_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(full_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


_load_submodule("const")
_load_submodule("incident")
