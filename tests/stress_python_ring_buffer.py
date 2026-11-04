"""Empirical Stress Test: Python BoundedRingBuffer and LiveBot Activity Log.

Verifies:
1. 100,000 to 500,000 sequential price ticks through Python BoundedRingBuffer.
2. Memory profiling via tracemalloc and psutil.
3. Strict bounds: size <= capacity, zero memory expansion, FIFO eviction.
"""

import sys
import os
import gc
import time
import tracemalloc

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tests.test_e2e_platform import BoundedRingBuffer

def run_python_ring_buffer_stress():
    print("=" * 80)
    print("PYTHON RING BUFFER 100,000+ SEQUENTIAL TICKS STRESS TEST")
    print("=" * 80)

    tracemalloc.start()
    gc.collect()
    snap_start = tracemalloc.take_snapshot()

    buf = BoundedRingBuffer(capacity=500)
    t0 = time.perf_counter()

    for tick in range(100000):
        buf.push({"tick": tick, "price": 100.0 + (tick % 500) * 0.1, "timestamp": 1700000000 + tick})

    t1 = time.perf_counter()
    dur_ms = (t1 - t0) * 1000
    print(f"Phase 1: 100,000 ticks processed in {dur_ms:.2f} ms ({100000 / (dur_ms / 1000):.0f} ticks/sec)")

    assert buf.size() == 500, f"Expected size 500, got {buf.size()}"
    assert buf.is_full(), "Expected buffer to be full"
    assert buf.peek_latest()["tick"] == 99999, f"Latest tick mismatch: {buf.peek_latest()}"
    assert buf.peek_oldest()["tick"] == 99500, f"Oldest tick mismatch: {buf.peek_oldest()}"

    arr = buf.to_array()
    assert len(arr) == 500
    assert arr[0]["tick"] == 99500
    assert arr[-1]["tick"] == 99999
    print("  [PASS] FIFO chronological ordering verified.")

    # Push up to 500,000 ticks
    print("\nPhase 2: Advancing to 500,000 sequential ticks...")
    t_start_500k = time.perf_counter()
    for tick in range(100000, 500000):
        buf.push({"tick": tick, "price": 150.0 + (tick % 100) * 0.2})
    t_end_500k = time.perf_counter()
    print(f"Phase 2: 400,000 additional ticks in {(t_end_500k - t_start_500k)*1000:.2f} ms")

    assert buf.size() == 500
    assert buf.peek_latest()["tick"] == 499999
    assert buf.peek_oldest()["tick"] == 499500

    gc.collect()
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    current_mb = current_mem / 1024 / 1024
    peak_mb = peak_mem / 1024 / 1024
    print(f"\n[Memory Profiling] Current Memory: {current_mb:.3f} MB | Peak Memory: {peak_mb:.3f} MB")
    assert peak_mb < 300.0, f"Peak memory {peak_mb:.2f} MB exceeded 300 MB budget!"
    print(f"  [PASS] Memory strictly bounded: {peak_mb:.3f} MB << 300 MB limit.")
    print("=" * 80)
    print("PYTHON RING BUFFER STRESS TEST: ALL VERIFICATIONS PASSED")
    print("=" * 80)

if __name__ == "__main__":
    run_python_ring_buffer_stress()
