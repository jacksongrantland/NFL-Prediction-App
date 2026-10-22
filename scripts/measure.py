"""Explicit local CPU benchmark. Does not fetch data or rescore a held-out test."""

import argparse
import ctypes
import json
import platform
import sys
import time
from pathlib import Path

from nfl_prediction.models.games import train
from nfl_prediction.refresh import RefreshConfig, atomic_json, refresh


def peak_working_set():
    if sys.platform != "win32":
        import resource

        return int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * (1 if sys.platform == "darwin" else 1024)
        )
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak_working_set",
                "working_set",
                "peak_paged_pool",
                "paged_pool",
                "peak_nonpaged_pool",
                "nonpaged_pool",
                "pagefile",
                "peak_pagefile",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.windll.psapi
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(Counters),
        wintypes.DWORD,
    ]
    if not psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counters), ctypes.sizeof(counters)
    ):
        raise OSError("Could not query this process memory counter")
    return int(counters.peak_working_set)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/refresh.local.json"))
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/release_measurements_2026-10-21.json")
    )
    args = parser.parse_args()
    settings = RefreshConfig.model_validate_json(args.config.read_text(encoding="utf-8-sig"))
    started = time.perf_counter()
    model = train(args.features, settings.artifacts_dir / "reproduction-game-models")
    training = time.perf_counter() - started
    training_peak = peak_working_set()
    updated = refresh(settings, fetch_sources=False)
    setup = {}
    for kind, name in [
        ("python", "repro-python-setup.json"),
        ("frontend", "repro-frontend-setup.json"),
    ]:
        path = Path("artifacts") / name
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            setup[kind] = {"kind": value["kind"], "elapsed_seconds": value["elapsed_seconds"]}
    report = {
        "date": "2026-10-21",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "setup_scope": "Existing runtimes; new environments and initially empty dependency caches",
        "cold_dependency_setup": setup,
        "game_training_wrapper_seconds": round(training, 3),
        "game_training_internal_seconds": model["elapsed_seconds"],
        "game_training_peak_working_set_bytes": training_peak,
        "game_training_test_evaluated": model["test_evaluated"],
        "refresh_seconds": updated["elapsed_seconds"],
        "refresh_peak_working_set_bytes": peak_working_set(),
        "refresh_draws_per_game": settings.count,
        "refresh_run_id": updated["run_id"],
        "refresh_steps": updated["steps"],
        "data_bytes": sum(p.stat().st_size for p in settings.data_dir.rglob("*") if p.is_file()),
        "artifact_bytes_including_reproduction_scratch": sum(
            p.stat().st_size for p in settings.artifacts_dir.parent.rglob("*") if p.is_file()
        ),
        "measurement_policy": (
            "Wall clock includes IO/function work after imports. Peak memory is "
            "process peak, not incremental model allocation. No network fetch or holdout rescore."
        ),
    }
    atomic_json(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k != "refresh_steps"}, indent=2))


if __name__ == "__main__":
    main()
