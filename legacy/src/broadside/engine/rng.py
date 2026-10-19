# Seeded, campaign-wide random number generation.
#
# Every system that needs randomness should take an RNG instance (or use
# CampaignRNG.stream(name) to get a private, still-deterministic sub-stream)
# rather than calling the stdlib `random` module or `numpy.random` globally.
# This is what keeps the simulation reproducible: same seed in, same
# campaign out, tick for tick. See docs/design/01_architecture.md.

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass, field

import numpy as np


def _stable_substream_seed(seed: int, *parts: str) -> int:
    """A reproducible-across-processes seed derived from `seed` and `parts`.

    Deliberately NOT using Python's built-in `hash()` on strings here: str
    hashing is salted per-process (PYTHONHASHSEED) unless explicitly
    disabled, which would silently break the "same seed -> same campaign"
    guarantee this whole module exists to provide. zlib.crc32 is stable.
    """
    payload = f"{seed}:{':'.join(parts)}".encode("utf-8")
    return zlib.crc32(payload) & 0xFFFFFFFF


@dataclass
class CampaignRNG:
    """Deterministic RNG rooted at a single campaign seed.

    `stream(name)` hands out an independent-but-deterministic RNG for a
    named subsystem (e.g. "wind", "crew_names", "combat") derived from the
    campaign seed. Independent streams mean, for example, that adding a new
    kind of random draw to the wind system won't shift the sequence of
    numbers the crew-name generator was drawing, which would otherwise make
    old replays/bug-reports drift for unrelated reasons.
    """

    seed: int
    _streams: dict[str, random.Random] = field(default_factory=dict, repr=False)
    _np_streams: dict[str, np.random.Generator] = field(default_factory=dict, repr=False)

    def stream(self, name: str) -> random.Random:
        if name not in self._streams:
            # Mix the stream name into the seed so each named stream is
            # independent but still fully determined by the campaign seed.
            stream_seed = _stable_substream_seed(self.seed, name)
            self._streams[name] = random.Random(stream_seed)
        return self._streams[name]

    def np_stream(self, name: str) -> np.random.Generator:
        """Like `stream`, but returns a numpy Generator for vectorised draws
        (e.g. sampling noise across a whole wind-cell grid at once)."""
        if name not in self._np_streams:
            stream_seed = _stable_substream_seed(self.seed, "np", name)
            self._np_streams[name] = np.random.default_rng(stream_seed)
        return self._np_streams[name]
