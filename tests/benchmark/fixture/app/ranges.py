from typing import List, Tuple


def chunk_ranges(total: int, size: int) -> List[Tuple[int, int]]:
    """Split ``range(total)`` into consecutive half-open ``(start, end)`` chunks.

    Every chunk has ``size`` items except possibly the last one, which holds
    whatever remains. ``total == 0`` gives an empty list. ``size`` must be
    positive and ``total`` must not be negative, otherwise ``ValueError``.

    >>> chunk_ranges(6, 3)
    [(0, 3), (3, 6)]
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if total < 0:
        raise ValueError("total must not be negative")
    chunks = []
    for i in range(total // size):
        start = i * size
        chunks.append((start, start + size))
    return chunks
