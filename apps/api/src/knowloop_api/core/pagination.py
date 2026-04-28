from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

T = TypeVar("T")


def collect_descending_page(
    items: Iterable[T],
    *,
    key: Callable[[T], Any],
    limit: int,
    offset: int = 0,
) -> tuple[list[T], int]:
    window_size = max(limit + offset, 0)
    heap: list[tuple[Any, int, T]] = []
    total = 0

    for sequence, item in enumerate(items):
        total += 1
        if window_size == 0:
            continue
        entry = (key(item), sequence, item)
        if len(heap) < window_size:
            heapq.heappush(heap, entry)
            continue
        if entry[:2] > heap[0][:2]:
            heapq.heapreplace(heap, entry)

    ordered_items = [
        entry[2]
        for entry in sorted(
            heap,
            key=lambda entry: (entry[0], entry[1]),
            reverse=True,
        )
    ]
    return ordered_items[offset : offset + limit], total
