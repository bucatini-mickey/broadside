# Map memory: which parts of the world the player's view has ever shown.
#
# Cataclysm-style: ground you have seen stays drawn, dimmed, after it goes
# out of sight; ground you have never seen is blank. Terrain is static, so
# memory only needs a "seen" flag per area - the remembered glyph is just
# the terrain drawn in memory colours. Moving things (ships) are *not*
# remembered here: that's the sim's contact records, which know where a
# ship was last seen rather than pretending it's still there.
#
# Stored as sparse 64x64 chunks at several resolutions (1 m, 4 m, 16 m,
# 64 m, 256 m cells) so a glance at the chart and a stroll along the deck
# both write memory at a sensible granularity. Each level keeps two masks:
#
#   native - marked by a view at that level's own resolution;
#   agg    - native, plus anything marked natively at a *finer* level.
#
# A read at level L is "seen" if agg[L] is set (you looked here at this
# scale or closer), or if any *coarser* level was marked natively (you
# glimpsed it on the chart - known, but only blockily). What a read never
# does is let one cell seen up close make its whole coarse block look
# explored when you zoom back in.

from __future__ import annotations

import numpy as np

LEVELS_M = (1.0, 4.0, 16.0, 64.0, 256.0)
CHUNK = 64


class _Level:
    def __init__(self, size: float):
        self.size = size
        self.native: dict[tuple[int, int], np.ndarray] = {}
        self.agg: dict[tuple[int, int], np.ndarray] = {}


def _chunks(cx: np.ndarray, cy: np.ndarray):
    """The chunk keys a batch of cells falls in. A view spans only a few, so
    walking the bounding rectangle beats sorting the whole batch - and
    writing the same cell twice costs nothing."""
    if cx.size == 0:
        return
    for kx in range(int(cx.min()), int(cx.max()) + 1):
        in_col = cx == kx
        if not in_col.any():
            continue
        col_y = cy[in_col]
        for ky in range(int(col_y.min()), int(col_y.max()) + 1):
            sel = in_col & (cy == ky)
            if sel.any():
                yield kx, ky, sel


def _write(store: dict, ix: np.ndarray, iy: np.ndarray) -> None:
    for kx, ky, sel in _chunks(ix // CHUNK, iy // CHUNK):
        chunk = store.get((kx, ky))
        if chunk is None:
            chunk = np.zeros((CHUNK, CHUNK), dtype=bool)
            store[(kx, ky)] = chunk
        chunk[iy[sel] - ky * CHUNK, ix[sel] - kx * CHUNK] = True


def _read(store: dict, ix: np.ndarray, iy: np.ndarray) -> np.ndarray:
    out = np.zeros(ix.size, dtype=bool)
    if not store:
        return out
    for kx, ky, sel in _chunks(ix // CHUNK, iy // CHUNK):
        chunk = store.get((kx, ky))
        if chunk is not None:
            out[sel] = chunk[iy[sel] - ky * CHUNK, ix[sel] - kx * CHUNK]
    return out


class MapMemory:
    def __init__(self) -> None:
        self._levels = [_Level(s) for s in LEVELS_M]

    @staticmethod
    def level_for(cell_m: float) -> int:
        for i, size in enumerate(LEVELS_M):
            if size >= cell_m * 0.99:
                return i
        return len(LEVELS_M) - 1

    def mark(self, xs: np.ndarray, ys: np.ndarray, seen: np.ndarray, cell_m: float) -> None:
        mask = np.asarray(seen).ravel()
        xs = np.asarray(xs, dtype=np.float64).ravel()[mask]
        ys = np.asarray(ys, dtype=np.float64).ravel()[mask]
        if xs.size == 0:
            return
        base = self.level_for(cell_m)
        for li in range(base, len(LEVELS_M)):
            lvl = self._levels[li]
            ix = np.floor(xs / lvl.size).astype(np.int64)
            iy = np.floor(ys / lvl.size).astype(np.int64)
            if li == base:
                _write(lvl.native, ix, iy)
            _write(lvl.agg, ix, iy)

    def seen(self, xs: np.ndarray, ys: np.ndarray, cell_m: float) -> np.ndarray:
        shape = np.shape(xs)
        xs = np.asarray(xs, dtype=np.float64).ravel()
        ys = np.asarray(ys, dtype=np.float64).ravel()
        base = self.level_for(cell_m)
        lvl = self._levels[base]
        out = _read(lvl.agg, np.floor(xs / lvl.size).astype(np.int64), np.floor(ys / lvl.size).astype(np.int64))
        for li in range(base + 1, len(LEVELS_M)):
            todo = ~out
            if not todo.any():
                break
            lvl = self._levels[li]
            if not lvl.native:
                continue
            idx = np.nonzero(todo)[0]
            out[idx] = _read(lvl.native, np.floor(xs[idx] / lvl.size).astype(np.int64), np.floor(ys[idx] / lvl.size).astype(np.int64))
        return out.reshape(shape)

    def clear(self) -> None:
        self._levels = [_Level(s) for s in LEVELS_M]
