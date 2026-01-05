from dataclasses import dataclass
from datetime import datetime

import pytest

from contree_sdk.sdk.client._registry import RelationsRegistry


@dataclass(unsafe_hash=True)
class _Object:
    v: int


def test_relations_basic():
    registry = RelationsRegistry[_Object](keep_n=1)
    a, b, c, d = (_Object(_) for _ in range(4))
    registry.add_relation(a, b)
    registry.add_relation(b, c)
    registry.add_relation(b, d)

    # all relations are available when objects are loaded into the memory
    assert registry.get_children(b) == {c, d}
    assert registry.get_children(c) == set()
    assert registry.get_parent(c) == b
    assert registry.get_parent(b) == a

    del b, c, d

    # but once we delete it locally we can get only up to 1 level (since registry has keep_n=1)
    assert next(iter(registry.get_children(a))).v == 1
    with pytest.raises(KeyError):
        registry.get_children(next(iter(registry.get_children(a))))


def test_relations_big_amount():
    keep_n = 5000
    started = datetime.now()
    registry = RelationsRegistry[_Object](keep_n=keep_n)
    obj = _Object(0)
    for i in range(int(keep_n * 1.25)):
        new_obj = _Object(i)
        registry.add_relation(obj, new_obj)
        obj = new_obj

    i = 0

    with pytest.raises(KeyError):
        while True:
            obj = registry.get_parent(obj)
            i += 1

            if i > keep_n:
                break

    assert i == keep_n - 2

    with pytest.raises(KeyError):
        registry.get_parent(obj)

    spent = datetime.now() - started

    # check that algorythm is O(1)
    assert spent.total_seconds() < keep_n / 10 / 1000
