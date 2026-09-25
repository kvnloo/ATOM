# SPDX-License-Identifier: MIT
"""Reproduce only the two pinned dense logging expressions with synthetic data.

Does not import ATOM, call a transfer, or observe GPU timings. Requires the exact
inspected dense source; no statements except its logger.info expressions run.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

EXPECTED_BLOB = "54e3cee334f007df7c4c9aa88b8ac63fc02fa1e6"
TIMINGS = ("pack_ms", "copy_ms", "sync_ms", "transfer_ms", "effective_gbps")


def check(path: Path) -> dict:
    raw = path.read_bytes()
    actual = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if actual != EXPECTED_BLOB:
        raise ValueError("Dense source differs from the inspected pin")
    calls = [node for node in ast.walk(ast.parse(raw))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name) and node.func.value.id == "logger"
             and node.func.attr == "info" and node.args
             and isinstance(node.args[0], ast.Constant)
             and isinstance(node.args[0].value, str)
             and node.args[0].value.startswith(("[OFFLOAD-SAVE-PROF]", "[OFFLOAD-LOAD-PROF]"))]
    if len(calls) != 2:
        raise ValueError("Expected exactly the load and save profiling expressions")
    reports = []
    for node in sorted(calls, key=lambda call: call.lineno):
        logs = []
        environment = {
            "logger": SimpleNamespace(info=lambda fmt, *args: logs.append(fmt % args)),
            "self": SimpleNamespace(_rank=0), "req": SimpleNamespace(req_id="synthetic"),
            "hbm": 0, "lmc": 16, "loaded": True,
            "ret_mask": SimpleNamespace(sum=lambda: SimpleNamespace(item=lambda: 16)),
            "toks": list(range(16)), "skip": 0,
            "retrieve_ms": 2.5, "store_ms": 2.5, "total_ms": 3.0,
        }
        expression = ast.Expression(node)
        code = compile(ast.fix_missing_locations(expression), str(path), "eval")
        count_only = {"stats_available": 1, "counts_available": 1,
                      "total_bytes": 128, "producer_fenced": 1}
        for extras in ({}, dict.fromkeys(TIMINGS, 0.0), dict.fromkeys(TIMINGS, 1.25)):
            environment["transfer_stats"] = count_only | extras
            eval(code, {"__builtins__": {"getattr": getattr, "len": len, "int": int, "float": float}}, environment)
        if logs[0] != logs[1]:
            raise AssertionError("Expected absent timing to be indistinguishable from explicit zero")
        for field in TIMINGS:
            if f"{field}=0.00" not in logs[0] or f"{field}=1.25" not in logs[2]:
                raise AssertionError("Unexpected logging contract")
        reports.append({"source_line": node.lineno, "absent_timing": logs[0],
                        "explicit_zero": logs[1], "populated_timing": logs[2]})
    return {"status": "LOG_EXPRESSION_BEHAVIOR_CONFIRMED", "source_blob": actual,
            "reports": reports, "input": "SYNTHETIC_COUNT_ONLY_STATS",
            "full_worker_execution": "NOT_RUN", "gpu": "NOT_RUN",
            "meaning": "Absent phase timings are formatted as 0.00, not measured to be zero."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dense_source", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.dense_source), indent=2))
