"""Both stores implement the whole persistence interface (api/store_protocols.py).

Services used to probe a store for a method and fall back to something else
when it was missing, so an incomplete store degraded silently. They now call
the interface directly. These tests keep production and the in-memory store
complete, so a missing method fails here rather than at a call site.
"""

import inspect

import pytest

from api import store_protocols
from api.store import AppStore, SupabaseAppStore
from tests.support import FakeStore

AREAS = [
    area
    for name, area in vars(store_protocols).items()
    if inspect.isclass(area) and name.endswith("Store") and area is not AppStore
]


def _methods(area) -> dict:
    return {
        name: member
        for name, member in vars(area).items()
        if callable(member) and not name.startswith("_")
    }


def _all_methods() -> dict:
    return {name: member for area in AREAS for name, member in _methods(area).items()}


def test_each_method_belongs_to_exactly_one_area():
    seen: dict[str, str] = {}
    for area in AREAS:
        for name in _methods(area):
            assert name not in seen, f"{name} is in both {seen[name]} and {area.__name__}"
            seen[name] = area.__name__


def test_app_store_is_every_area():
    assert set(AppStore.__mro__) >= set(AREAS)


@pytest.mark.parametrize("store_class", [SupabaseAppStore, FakeStore], ids=lambda cls: cls.__name__)
def test_store_implements_the_whole_interface(store_class):
    missing = sorted(name for name in _all_methods() if not callable(getattr(store_class, name, None)))

    assert missing == []


@pytest.mark.parametrize("store_class", [SupabaseAppStore, FakeStore], ids=lambda cls: cls.__name__)
def test_store_accepts_every_declared_parameter(store_class):
    mismatches = []
    for name, declared in _all_methods().items():
        implemented = inspect.signature(getattr(store_class, name)).parameters
        if any(param.kind is param.VAR_KEYWORD for param in implemented.values()):
            continue
        absent = [
            param
            for param, spec in inspect.signature(declared).parameters.items()
            if param != "self" and spec.kind is not spec.VAR_KEYWORD and param not in implemented
        ]
        if absent:
            mismatches.append((name, absent))

    assert mismatches == []
