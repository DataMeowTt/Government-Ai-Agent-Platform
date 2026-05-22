from __future__ import annotations

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


if "pydantic_settings" not in sys.modules:
    module = types.ModuleType("pydantic_settings")

    class BaseSettings:
        def __init__(self, **kwargs):
            for key, value in self.__class__.__dict__.items():
                if key.startswith("_") or callable(value):
                    continue
                setattr(self, key, value)
            for key, value in kwargs.items():
                setattr(self, key, value)

    class SettingsConfigDict(dict):
        pass

    module.BaseSettings = BaseSettings
    module.SettingsConfigDict = SettingsConfigDict
    sys.modules["pydantic_settings"] = module
