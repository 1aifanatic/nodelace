from __future__ import annotations

import statistics
import time

import pytest

from nodelace import render
from nodelace.renderer import DiagramDensityWarning


@pytest.mark.filterwarnings(f"ignore::{DiagramDensityWarning.__module__}.DiagramDensityWarning")
def test_maximum_node_fanout_renders_well_below_one_second() -> None:
    source = "\n".join(
        (
            'architecture "Maximum fan-out"',
            "direction left-to-right",
            *(f"Hub -> Node {index}: route {index}" for index in range(1, 50)),
        )
    )

    # Warm interpreter and resource caches, then measure the complete public
    # parse/layout/SVG path. The 1 s gate leaves ample headroom for shared CI.
    render(source, embed_fonts=False)
    samples: list[float] = []
    outputs: list[str] = []
    for _ in range(5):
        started = time.perf_counter()
        outputs.append(render(source, embed_fonts=False))
        samples.append(time.perf_counter() - started)

    assert len(set(outputs)) == 1
    assert statistics.median(samples) < 1.0
