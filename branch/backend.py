"""Array backend selection: NumPy (CPU) or CuPy (NVIDIA GPU, e.g. DGX Spark).

The same code runs on both. Select with the environment variable
BRANCH_BACKEND=numpy|cupy or by passing a name to get_xp().
"""
import os
import time
from typing import Any, Optional

import numpy as np


def get_xp(name: Optional[str] = None) -> Any:
    name = (name or os.environ.get("BRANCH_BACKEND", "numpy")).lower()
    if name == "cupy":
        import cupy as cp  # noqa: WPS433
        return cp
    if name != "numpy":
        raise ValueError(f"Unknown backend {name!r}")
    return np


def is_gpu(xp: Any) -> bool:
    return xp.__name__ == "cupy"


def to_numpy(a: Any) -> Any:
    return a.get() if hasattr(a, "get") else np.asarray(a)


def sync(xp: Any) -> None:
    """Block until queued GPU work finishes, so timings are honest."""
    if is_gpu(xp):
        xp.cuda.Stream.null.synchronize()


class Timer:
    def __init__(self, xp):
        self.xp = xp

    def __enter__(self):
        sync(self.xp)
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        sync(self.xp)
        self.seconds = time.perf_counter() - self.t0
