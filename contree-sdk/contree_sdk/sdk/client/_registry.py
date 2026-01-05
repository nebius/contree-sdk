from collections import Counter, defaultdict, deque
from collections.abc import Hashable
from typing import Generic, Protocol, TypeVar, runtime_checkable
from weakref import WeakValueDictionary, ref


@runtime_checkable
class RegistryItem(Protocol):
    def __key__(self) -> Hashable: ...


T = TypeVar("T", bound=Hashable | RegistryItem)


class RelationsRegistry(Generic[T]):
    def __init__(self, keep_n: int):
        self._objects: WeakValueDictionary = WeakValueDictionary()
        self._parents: dict[Hashable, Hashable] = {}
        self._children: dict[Hashable, set[Hashable]] = defaultdict(set)

        self.keep_n = keep_n
        self._ref_queue: deque[ref[T]] = deque()
        self._strong_counter: Counter[T] = Counter[T]()

    def _cleanup(self):
        while len(self._strong_counter) > self.keep_n:
            evicted = self._ref_queue.popleft()()
            if evicted is None:  # already deleted
                continue
            self._del_element(evicted)

    def _del_element(self, element: T):
        self._strong_counter[element] -= 1
        if self._strong_counter[element] <= 0:
            del self._strong_counter[element]

    def add_element(self, element: T):
        self._ref_queue.append(ref(element))
        self._strong_counter[element] += 1
        self._cleanup()

    def add_relation(self, parent: T, child: T):
        parent_hash = self._get_hash(parent)
        child_hash = self._get_hash(child)
        self._objects[parent_hash] = parent
        self._objects[child_hash] = child

        self._parents[child_hash] = parent_hash
        self._children[parent_hash].add(child_hash)

        self.add_element(child)
        self.add_element(parent)

    def _get_hash(self, item: T) -> Hashable:
        if isinstance(item, RegistryItem):
            return item.__key__()
        return hash(item)

    def get_children(self, parent: Hashable) -> set[Hashable]:
        result = set()
        for child_hash in self._children[hash(parent)]:
            result.add(self._objects[child_hash])
        return result

    def get_parent(self, child: Hashable) -> Hashable:
        child_hash = hash(child)
        return self._objects[self._parents[child_hash]]
