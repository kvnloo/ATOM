"""Downstream review rule, not a log parser or a GPU correctness test.

Callers must first validate the pinned recipe's result fields, exit code and
provenance, then supply the complete, manually reviewed error-message list.
The output NEVER certifies process cleanup, including when no errors are seen.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

KNOWN = "Error closing backend LocalCPUBackend: tuple index out of range"


def classify(*, version: str, exit_code: int | None,
             transfer_valid: bool | None, diagnostics_reviewed: bool,
             errors: tuple[str, ...]) -> dict[str, str]:
    cleanup = "UNKNOWN_REQUIRES_SEPARATE_OBSERVATION"
    if type(exit_code) is not int:
        status = "INCOMPLETE_PROCESS_RESULT"
    elif exit_code != 0:
        status = "BLOCKED_PROCESS_RESULT"
    elif transfer_valid is not True:
        status = "BLOCKED_OR_INCOMPLETE_TRANSFER_RESULT"
    elif diagnostics_reviewed is not True:
        status = "NEEDS_DIAGNOSTIC_REVIEW"
    elif version != "0.4.5":
        status = "OUTSIDE_PINNED_ENVIRONMENT"
    elif any(message != KNOWN for message in errors):
        status = "NEEDS_DIAGNOSTIC_REVIEW"
    elif errors:
        status = "BOUNDED_TRANSFER_WITH_KNOWN_TEARDOWN_LOG"
    else:
        status = "BOUNDED_TRANSFER_NO_REPORTED_ERRORS"
    return {"transfer_review": status, "process_cleanup": cleanup}


def main() -> None:
    good = dict(version="0.4.5", exit_code=0, transfer_valid=True,
                diagnostics_reviewed=True, errors=())
    cases = [
        ("no_reported_errors", {}, "BOUNDED_TRANSFER_NO_REPORTED_ERRORS"),
        ("author_known_log", {"errors": (KNOWN,)}, "BOUNDED_TRANSFER_WITH_KNOWN_TEARDOWN_LOG"),
        ("unreviewed_log", {"diagnostics_reviewed": False}, "NEEDS_DIAGNOSTIC_REVIEW"),
        ("different_message", {"errors": ("device failed",)}, "NEEDS_DIAGNOSTIC_REVIEW"),
        ("known_plus_new_error", {"errors": (KNOWN, "device failed")}, "NEEDS_DIAGNOSTIC_REVIEW"),
        ("different_dependency", {"version": "0.5.6", "errors": (KNOWN,)}, "OUTSIDE_PINNED_ENVIRONMENT"),
        ("known_log_nonzero_exit", {"exit_code": 1, "errors": (KNOWN,)}, "BLOCKED_PROCESS_RESULT"),
        ("known_log_failed_transfer", {"transfer_valid": False, "errors": (KNOWN,)}, "BLOCKED_OR_INCOMPLETE_TRANSFER_RESULT"),
        ("missing_exit", {"exit_code": None}, "INCOMPLETE_PROCESS_RESULT"),
        ("boolean_exit_is_not_zero", {"exit_code": False}, "INCOMPLETE_PROCESS_RESULT"),
        ("missing_transfer_verdict", {"transfer_valid": None}, "BLOCKED_OR_INCOMPLETE_TRANSFER_RESULT"),
        ("integer_transfer_is_not_boolean", {"transfer_valid": 1}, "BLOCKED_OR_INCOMPLETE_TRANSFER_RESULT"),
    ]
    observations = []
    for name, changes, expected in cases:
        result = classify(**(good | changes))
        if result["transfer_review"] != expected:
            raise AssertionError((name, result, expected))
        if result["process_cleanup"] != "UNKNOWN_REQUIRES_SEPARATE_OBSERVATION":
            raise AssertionError("A transfer result must not certify cleanup")
        observations.append({"case": name, "result": result, "check": "PASS"})
    report = {"status": "SYNTHETIC_CONTRACT_CHECKS_PASSED", "cases": observations,
              "python": sys.version, "gpu": "NOT_RUN", "real_log_reproduction": "NOT_RUN",
              "source": "https://github.com/ROCm/ATOM/pull/2339#issuecomment-5831522164"}
    Path(__file__).with_name("teardown_contract_results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "cases": len(observations), "gpu": "NOT_RUN"}))


if __name__ == "__main__":
    main()
