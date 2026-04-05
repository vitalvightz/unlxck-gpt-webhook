from __future__ import annotations

import importlib
import sys
import types


def test_root_main_re_exports_api_app_entrypoint():
    sentinel_app = object()
    sentinel_factory = object()
    fake_api_app = types.ModuleType("api.app")
    fake_api_app.app = sentinel_app
    fake_api_app.create_app = sentinel_factory

    previous_main = sys.modules.pop("main", None)
    previous_api_app = sys.modules.get("api.app")
    sys.modules["api.app"] = fake_api_app

    try:
        imported = importlib.import_module("main")
        assert imported.app is sentinel_app
        assert imported.create_app is sentinel_factory
    finally:
        sys.modules.pop("main", None)
        if previous_main is not None:
            sys.modules["main"] = previous_main
        if previous_api_app is not None:
            sys.modules["api.app"] = previous_api_app
        else:
            sys.modules.pop("api.app", None)
