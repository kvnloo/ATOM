# SPDX-License-Identifier: MIT
"""Fork-only CPU experiment; writes only disposable worktrees and receipts."""

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

BASE = "a5ad0a5086af9042fd23823392f59781d4806894"
BLOB = "3b3d69581315071f308ec9b81b00cb06b641d520"
PRODUCTION = Path("atom/kv_transfer/offload/dense/connector.py")
PROBE = Path("tests/test_dense_lookup_initialization.py")
FOCUSED = "tests/test_dense_offload_connector.py"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = Path(os.environ.get("QUALIFICATION_OUT", ROOT / "qualification-results")).resolve()
OUT.mkdir(parents=True, exist_ok=False)
WORK = Path(tempfile.mkdtemp(prefix="atom-lookup-qualification-"))
RECEIPT = {
    "base_commit": BASE,
    "base_production_blob": BLOB,
    "scope": "CPU production-constructor tests with external dependency fakes",
    "hardware_qualification": "NOT_RUN",
    "real_lmcache_integration": "NOT_RUN",
    "upstream_publication": "NONE",
    "python": sys.version,
    "platform": platform.platform(),
    "experiment_commit": os.environ.get("GITHUB_SHA"),
    "github_run_id": os.environ.get("GITHUB_RUN_ID"),
    "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    "commands": [],
    "status": "IN_PROGRESS",
}


def save_receipt():
    (OUT / "receipt.json").write_text(json.dumps(RECEIPT, indent=2) + "\n")


def run(name, args, cwd, timeout=900, extra_env=None):
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(cwd),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
    )
    if extra_env:
        env.update(extra_env)
    log = OUT / f"{name}.log"
    with log.open("w") as stream:
        try:
            result = subprocess.run(
                args, cwd=cwd, env=env, stdout=stream,
                stderr=subprocess.STDOUT, timeout=timeout, check=False,
            )
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
            stream.write("\nEXPERIMENT_COMMAND_TIMEOUT\n")
    RECEIPT["commands"].append({
        "name": name, "argv": list(args), "cwd": str(cwd),
        "exit_code": code, "log": log.name,
    })
    print(f"{name}: exit={code}", flush=True)
    save_receipt()
    return code


def checked(args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def parse_report(name):
    path = OUT / f"{name}.xml"
    if not path.exists():
        return {"valid": False, "reason": "missing JUnit report", "cases": {}}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        return {"valid": False, "reason": str(error), "cases": {}}
    cases = {}
    for item in root.iter("testcase"):
        key = item.get("classname", "") + "::" + item.get("name", "")
        if key in cases:
            return {"valid": False, "reason": "duplicate testcase", "cases": cases}
        status, detail = "passed", ""
        for kind in ["error", "failure", "skipped"]:
            child = item.find(kind)
            if child is not None:
                status = kind
                detail = child.get("message", "") + "\n" + (child.text or "")
                break
        cases[key] = {"status": status, "detail": detail}
    return {"valid": bool(cases), "cases": cases}


def pytest(name, cwd, *selection):
    return run(name, [
        sys.executable, "-m", "pytest", *selection,
        "-q", "-rs", f"--junitxml={OUT / (name + '.xml')}",
    ], cwd)


def apply_candidate(path):
    text = path.read_text()
    replacements = [
        (
            '            logger.warning("LMCache offload: lookup server not started: %s", e)',
            '            logger.warning(\n'
            '                "LMCache offload: lookup server not started: error_type=%s",\n'
            '                type(e).__name__,\n'
            '            )',
        ),
        (
            '                "LMCache offload scheduler: lookup client unavailable: %s", e',
            '                "LMCache offload scheduler: lookup client unavailable: "\n'
            '                "error_type=%s",\n'
            '                type(e).__name__,',
        ),
    ]
    for old, new in replacements:
        if text.count(old) != 1:
            raise RuntimeError("Pinned diagnostic boundary drifted; refuse to patch")
        text = text.replace(old, new, 1)
    path.write_text(text)


def probe_gate(control, candidate, sensitivity):
    a, b, c = [parse_report(name) for name in (control, candidate, sensitivity)]
    if not all(report["valid"] for report in (a, b, c)):
        return False
    if not (a["cases"].keys() == b["cases"].keys() == c["cases"].keys()):
        return False
    # Declared matrix: 2 components x 4 roles x 2 exception strings, plus
    # 8 successful constructions, 4 non-hosting roles and 1 ordinary miss.
    if len(a["cases"]) != 29:
        return False
    expected_red = {
        key for key in a["cases"]
        if "::test_lookup_initialization_exception_is_identifiable[" in key
    }
    if len(expected_red) != 16:
        return False
    for report in (a, c):
        for key, result in report["cases"].items():
            expected = "failure" if key in expected_red else "passed"
            if result["status"] != expected:
                return False
            if key in expected_red and "LOOKUP_DIAGNOSTIC_CLASS_MISSING" not in result["detail"]:
                return False
    return all(result["status"] == "passed" for result in b["cases"].values())


def main():
    save_receipt()
    paths = {label: WORK / label for label in ["baseline", "control", "candidate"]}
    for label, path in paths.items():
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(path), BASE],
            cwd=ROOT, check=True,
        )
        if checked(["git", "hash-object", str(PRODUCTION)], path) != BLOB:
            raise RuntimeError("Source blob does not match inspected production file")
        if checked(["git", "status", "--porcelain"], path):
            raise RuntimeError("New experiment worktree is not pristine")
    baseline, control, candidate = [paths[key] for key in ["baseline", "control", "candidate"]]
    frozen_before = checked([sys.executable, "-m", "pip", "freeze", "--all"])
    (OUT / "dependencies-before.txt").write_text(frozen_before + "\n")
    (OUT / "experiment-source-sha256.json").write_text(json.dumps({
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [HERE / "run.py", HERE / "lookup_tests.py"]
    }, indent=2) + "\n")
    for path in (baseline, control, candidate):
        run(f"{path.name}-import-origin", [sys.executable, "-c",
            "from pathlib import Path; "
            "from atom.kv_transfer.offload.dense import connector; "
            "p=Path(connector.__file__).resolve(); print(p); "
            "assert p == Path.cwd() / 'atom/kv_transfer/offload/dense/connector.py'"
        ], path)
    baseline_focus = pytest("baseline-focused", baseline, FOCUSED)
    for path in (control, candidate):
        shutil.copyfile(HERE / "lookup_tests.py", path / PROBE)
    # Format only the new test, using the pinned repository's Black settings.
    # Both comparison arms receive identical formatted bytes before execution.
    format_code = run("format-new-test", [sys.executable, "-m", "black", str(PROBE)], control)
    shutil.copyfile(control / PROBE, candidate / PROBE)
    RECEIPT["probe_sha256"] = hashlib.sha256((control / PROBE).read_bytes()).hexdigest()
    (OUT / "test_dense_lookup_initialization.py").write_bytes((control / PROBE).read_bytes())
    control_code = pytest("control-probe", control, str(PROBE))
    original = (candidate / PRODUCTION).read_bytes()
    apply_candidate(candidate / PRODUCTION)
    RECEIPT["candidate_production_blob"] = checked(["git", "hash-object", str(PRODUCTION)], candidate)
    candidate_probe = pytest("candidate-probe", candidate, str(PROBE))
    candidate_repeat = pytest("candidate-probe-repeat", candidate, str(PROBE))
    candidate_focus = pytest("candidate-focused", candidate, FOCUSED)
    subprocess.run(["git", "add", "--intent-to-add", str(PROBE)], cwd=candidate, check=True)
    checks = [
        format_code,
        run("black", [sys.executable, "-m", "black", "--check", str(PRODUCTION), str(PROBE)], candidate),
        run("ruff", [sys.executable, "-m", "ruff", "check", str(PRODUCTION), str(PROBE)], candidate),
        run("diff-check", ["git", "diff", "--check"], candidate),
    ]
    for label, path in [("baseline", baseline), ("candidate", candidate)]:
        run(f"{label}-native", ["bash", ".github/scripts/run_unit_tests.sh"], path,
            extra_env={"UNIT_TEST_REPORT": str(OUT / f"{label}-native.xml")})
    baseline_native = parse_report("baseline-native")
    candidate_native = parse_report("candidate-native")
    RECEIPT["native_suite"] = {
        "baseline": baseline_native, "candidate": candidate_native,
    }
    new_regressions = []
    lost_coverage = []
    changed_failure_details = []
    for key, result in candidate_native["cases"].items():
        previous = baseline_native["cases"].get(key)
        if result["status"] in {"failure", "error"} and (
            previous is None or previous["status"] != result["status"]
        ):
            new_regressions.append(key)
        if result["status"] in {"failure", "error"} and previous and previous["status"] == result["status"]:
            before = previous["detail"].replace(str(baseline), "<SOURCE_ROOT>")
            after = result["detail"].replace(str(candidate), "<SOURCE_ROOT>")
            if before != after:
                changed_failure_details.append(key)
        if result["status"] == "skipped" and (previous is None or previous["status"] != "skipped"):
            lost_coverage.append(key)
    lost_coverage.extend(set(baseline_native["cases"]) - set(candidate_native["cases"]))
    RECEIPT["native_new_regressions"] = sorted(new_regressions)
    RECEIPT["native_lost_coverage"] = sorted(lost_coverage)
    RECEIPT["native_changed_failure_details"] = sorted(changed_failure_details)
    native_probe_cases = {
        key: result for key, result in candidate_native["cases"].items()
        if "test_dense_lookup_initialization::" in key
    }
    native_probe_ok = len(native_probe_cases) == 29 and all(
        result["status"] == "passed" for result in native_probe_cases.values()
    )
    RECEIPT["native_probe_passed"] = native_probe_ok
    patch = subprocess.check_output(["git", "diff", "--binary", BASE, "--", str(PRODUCTION), str(PROBE)], cwd=candidate)
    (OUT / "candidate.patch").write_bytes(patch)
    RECEIPT["candidate_patch_sha256"] = hashlib.sha256(patch).hexdigest()
    patched = (candidate / PRODUCTION).read_bytes()
    try:
        (candidate / PRODUCTION).write_bytes(original)
        sensitivity_code = pytest("sensitivity-probe", candidate, str(PROBE))
    finally:
        (candidate / PRODUCTION).write_bytes(patched)
    frozen_after = checked([sys.executable, "-m", "pip", "freeze", "--all"])
    (OUT / "dependencies-after.txt").write_text(frozen_after + "\n")
    RECEIPT["dependencies_unchanged"] = frozen_before == frozen_after
    RECEIPT["probe_reports"] = {
        name: parse_report(name) for name in [
            "control-probe", "candidate-probe", "candidate-probe-repeat", "sensitivity-probe"
        ]
    }
    origins_ok = all(
        cmd["exit_code"] == 0 for cmd in RECEIPT["commands"]
        if cmd["name"].endswith("-import-origin")
    )
    native_codes_ok = all(
        cmd["exit_code"] in (0, 1) for cmd in RECEIPT["commands"]
        if cmd["name"].endswith("-native")
    )
    gate = (
        baseline_focus == candidate_focus == candidate_probe == candidate_repeat == 0
        and control_code == sensitivity_code == 1
        and probe_gate("control-probe", "candidate-probe", "sensitivity-probe")
        and baseline_native["valid"] and candidate_native["valid"]
        and not new_regressions and not lost_coverage
        and not changed_failure_details and native_probe_ok
        and all(code == 0 for code in checks) and origins_ok and native_codes_ok
        and RECEIPT["dependencies_unchanged"]
    )
    RECEIPT["status"] = "CPU_GATE_PASSED" if gate else "CPU_GATE_NOT_MET"
    RECEIPT["limits"] = [
        "No real LMCache binary, GPU, host-tier reload, accuracy or performance qualification.",
        "Native-suite pre-existing failures/skips are retained, not silently converted to passes.",
        "Candidate is a patch artifact, not a production commit or an upstream PR.",
    ]
    save_receipt()
    print(RECEIPT["status"], flush=True)
    return 0 if gate else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        RECEIPT["status"] = "EXPERIMENT_BLOCKED_OR_INVALID"
        RECEIPT["exception_type"] = type(error).__name__
        save_receipt()
        raise
