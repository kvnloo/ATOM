# SPDX-License-Identifier: MIT
"""Fork-only pinned CPU lanes; no server, model, GPU or upstream writes."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET

BASE = "68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e"
EARLY = "tests/test_offload_early_block_release.py"
DENSE = "tests/test_dense_offload_connector.py"
MP = "tests/test_lmcache_mp.py"
PROBE = "tests/test_rfc_mp_characterization.py"
AGGREGATOR = "atom/kv_transfer/disaggregation/aggregator.py"
MP_SOURCE = "atom/kv_transfer/offload/mp/backend.py"
DENSE_SOURCE = "atom/kv_transfer/offload/dense/connector.py"
REQUIRED_LIFETIMES = [
    "test_one_incomplete_rank_prevents_logical_group_release",
    "test_pre_submit_failure_retries_only_after_tp_source_quorum",
    "test_mixed_tp_outcome_waits_for_all_source_quiescent_reports",
    "test_live_post_submit_failure_retries_once_all_source_groups_are_safe",
    "test_commit_failure_after_source_safe_releases_without_success_stats",
    "test_late_completions_after_timeout_reclaim_are_noops",
    "test_duplicate_and_stale_source_completions_do_not_double_release",
    "test_request_id_reuse_cannot_attach_an_old_lease_to_new_blocks",
]
QUORUM_NODES = [
    EARLY + "::TestTPQuorum::test_one_incomplete_rank_prevents_logical_group_release",
    EARLY + "::TestStoreOutcomeSeparation::test_mixed_tp_outcome_waits_for_all_source_quiescent_reports",
]
REQUIRED_MP = [
    "test_submission_time_is_outside_the_polling_deadline",
    "test_slow_status_call_can_return_a_hit_after_the_poll_deadline",
    "test_direct_native_readers_do_not_adopt_vllm_only_options",
    "test_mp_lookup_timeout_defers_cleanup_until_result",
    "test_mp_lookup_timeout_is_not_recorded_as_a_tier_miss",
]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=["mp", "lifetimes"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    before = subprocess.check_output([sys.executable, "-m", "pip", "freeze", "--all"], text=True)
    (out / "dependencies-before.txt").write_text(before)
    receipt = {
        "status": "IN_PROGRESS", "lane": args.lane, "source": BASE,
        "run_id": os.environ.get("GITHUB_RUN_ID"), "python": sys.version,
        "full_native_suite": "NOT_RUN", "real_lmcache_binary": "NOT_QUALIFIED",
        "server": "NOT_STARTED", "gpu": "NOT_RUN", "commands": [],
    }
    probe_path = source / PROBE
    original_aggregator = None
    try:
        require(git(source, "rev-parse", "HEAD") == BASE, "Wrong source revision")
        require(not git(source, "status", "--porcelain"), "Dirty input checkout")
        snapshot_paths = [MP_SOURCE, DENSE_SOURCE, AGGREGATOR, EARLY, DENSE, MP, "tests/conftest.py"]
        receipt["source_sha256"] = {}
        for relative in snapshot_paths:
            path = source / relative
            data = path.read_bytes()
            receipt["source_sha256"][relative] = hashlib.sha256(data).hexdigest()
            target = out / "source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        tree = ast.parse((source / DENSE_SOURCE).read_text())
        warnings = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "warning":
                text = ast.unparse(node)
                if "lookup" in text.lower():
                    warnings.append({"line": node.lineno, "call": text})
        (out / "current-lookup-warnings.json").write_text(json.dumps(warnings, indent=2) + "\n")

        def run_tests(name, selection):
            report = out / (name + ".xml")
            command = [sys.executable, "-m", "pytest", "--trace-config", *selection,
                       "-q", "-rs", f"--junitxml={report}"]
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(source)
            with (out / (name + ".log")).open("w") as log:
                completed = subprocess.run(command, cwd=source, env=environment,
                    stdout=log, stderr=subprocess.STDOUT, timeout=300, check=False)
            require(str(source / "tests/conftest.py") in (out / (name + ".log")).read_text(), "Normal shared fixtures not observed")
            cases = []
            seen = set()
            for case in ET.parse(report).getroot().iter("testcase"):
                key = case.get("classname", "") + "::" + case.get("name", "")
                require(key not in seen, "Duplicate JUnit test identity")
                seen.add(key)
                status, detail = "passed", ""
                for tag in ["error", "failure", "skipped"]:
                    element = case.find(tag)
                    if element is not None:
                        status, detail = tag, element.get("message", "") + "\n" + (element.text or "")
                        break
                cases.append({"id": key, "name": case.get("name"), "status": status, "detail": detail})
            result = {"name": name, "argv": command, "exit_code": completed.returncode, "cases": cases}
            receipt["commands"].append(result)
            print(json.dumps({"arm": name, "exit": completed.returncode,
                "counts": {status: sum(c["status"] == status for c in cases) for status in ["passed", "failure", "error", "skipped"]}}), flush=True)
            return result

        if args.lane == "mp":
            require(not probe_path.exists(), "Characterization filename collision")
            shutil.copyfile(Path(__file__).with_name("mp_characterization.py"), probe_path)
            shutil.copyfile(probe_path, out / probe_path.name)
            baseline = run_tests("mp-and-characterization", [MP, PROBE])
            required = REQUIRED_MP
        else:
            baseline = run_tests("existing-lifetime-tests", [EARLY, DENSE])
            required = REQUIRED_LIFETIMES
        require(baseline["exit_code"] == 0, "Selected suite failed")
        for test_name in required:
            matches = [c for c in baseline["cases"] if c["name"] == test_name]
            require(len(matches) == 1 and matches[0]["status"] == "passed", "Required observation absent: " + test_name)
        if args.lane == "lifetimes":
            # In a disposable checkout only, remove the real all-ranks barrier
            # to show that existing tests detect premature memory release.
            path = source / AGGREGATOR
            original_aggregator = path.read_bytes()
            text = original_aggregator.decode()
            old = "if len(reports) < self._world_size:"
            require(text.count(old) == 1, "Quorum mutation seam drifted")
            try:
                path.write_text(text.replace(old, "if len(reports) < 1:", 1))
                broken = run_tests("premature-quorum-control", QUORUM_NODES)
                require(broken["exit_code"] == 1 and len(broken["cases"]) == 2, "Invalid sensitivity control")
                require(all(c["status"] == "failure" and "take_source_safe_releases() == []" in c["detail"] for c in broken["cases"]), "Control must fail at premature-release assertions")
            finally:
                path.write_bytes(original_aggregator)
            restored = run_tests("restored-quorum", QUORUM_NODES)
            require(restored["exit_code"] == 0 and len(restored["cases"]) == 2 and all(c["status"] == "passed" for c in restored["cases"]), "Restored quorum did not pass")
        after = subprocess.check_output([sys.executable, "-m", "pip", "freeze", "--all"], text=True)
        (out / "dependencies-after.txt").write_text(after)
        require(before == after, "Dependencies changed")
        require(not git(source, "diff", "--name-only"), "Tracked production/test source left changed")
        receipt["status"] = "PINNED_CPU_LANE_PASSED"
        receipt["dependencies_unchanged"] = True
        receipt["limits"] = [
            "Normal ATOM test fixtures loaded; selected tests only, not full native suite.",
            "MP timing uses a deterministic fake clock/adapter, not measured server latency.",
            "Lifetime sensitivity changes only a temporary CPU comparison, never a committed source file.",
            "Existing hardware coverage is not reproduced by these tests.",
        ]
        return 0
    except Exception as error:
        receipt["status"] = "LANE_BLOCKED_OR_GATE_NOT_MET"
        receipt["error_type"] = type(error).__name__
        receipt["error"] = str(error)
        (out / "exception.txt").write_text(traceback.format_exc())
        return 1
    finally:
        if original_aggregator is not None:
            (source / AGGREGATOR).write_bytes(original_aggregator)
        if args.lane == "mp" and probe_path.exists():
            probe_path.unlink()
        (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps({"lane": args.lane, "status": receipt["status"]}), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
