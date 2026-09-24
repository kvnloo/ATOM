# SPDX-License-Identifier: MIT
"""Downstream real-parser comparison. Does not start LMCache or modify its code."""
from __future__ import annotations

import argparse
import contextlib
import difflib
import hashlib
import importlib
import inspect
import io
import json
import logging
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import traceback

ATOM_SHA = "9c64bea07eeb16f75c746787490522abf0efbaec"
LMCACHE_SHA = "05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb"
README = Path("atom/kv_transfer/offload/README.md")
OLD_LINE = "  --supported-transfer-mode lmcache_driven --l1-size-gb 64"
EXPECTED = {
    "--host": "127.0.0.1", "--port": 5555, "--chunk-size": 256,
    "--null-block-id": -1, "--separate-object-groups": True,
    "--supported-transfer-mode": "lmcache_driven", "--l1-size-gb": 64,
}
MODULES = [
    "lmcache.cli.commands.server", "lmcache.v1.distributed.config",
    "lmcache.v1.mp_observability.config", "lmcache.v1.multiprocess.config",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def recipe(text: str) -> list[str]:
    heading = "### Running the MP server"
    require(text.count(heading) == 1, "README section drift")
    section = text.split(heading, 1)[1]
    match = re.search(r"```bash\n(.*?)\n```", section, flags=re.S)
    require(match is not None, "Missing server command block")
    words = shlex.split(match.group(1).replace("\\\n", " "))
    require(words[:2] == ["lmcache", "server"], "Unexpected command prefix")
    return words[2:]


class RegistrationLog(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--atom-root", type=Path, required=True)
    cli.add_argument("--lmcache-root", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    atom = args.atom_root.resolve(strict=True)
    lmcache = args.lmcache_root.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    receipt: dict = {
        "status": "IN_PROGRESS", "atom_sha": ATOM_SHA, "lmcache_sha": LMCACHE_SHA,
        "python": sys.version, "run_id": os.environ.get("GITHUB_RUN_ID"),
        "server_started": False, "gpu_test": "NOT_RUN",
        "binary_qualification": "NOT_RUN", "parser_mocks": False,
        "arms": {},
    }
    stage = "INPUT_VALIDATION"
    try:
        for root, expected in [(atom, ATOM_SHA), (lmcache, LMCACHE_SHA)]:
            require(git(root, "rev-parse", "HEAD") == expected, "Source SHA mismatch")
            require(not git(root, "status", "--porcelain"), "Input checkout is dirty")
        original = (atom / README).read_text()
        require(original.count(OLD_LINE) == 1, "Example line drift")
        candidate = original.replace(OLD_LINE, OLD_LINE + " --eviction-policy LRU", 1)
        before_args, after_args = recipe(original), recipe(candidate)
        require("--eviction-policy" not in before_args, "Example already corrected")
        require(after_args == before_args + ["--eviction-policy", "LRU"], "Nonminimal change")
        patch = "".join(difflib.unified_diff(
            original.splitlines(keepends=True), candidate.splitlines(keepends=True),
            fromfile=f"a/{README}", tofile=f"b/{README}",
        ))
        (out / "candidate.patch").write_text(patch)
        (out / "original-argv.json").write_text(json.dumps(before_args, indent=2) + "\n")
        receipt["readme_sha256"] = sha256(atom / README)
        receipt["patch_sha256"] = sha256(out / "candidate.patch")
        frozen_before = subprocess.check_output([sys.executable, "-m", "pip", "freeze", "--all"], text=True)
        (out / "dependencies-before.txt").write_text(frozen_before)
        stage = "ENVIRONMENT_IMPORT"
        sys.path.insert(0, str(lmcache))
        server = importlib.import_module(MODULES[0])
        expected_server = lmcache / "lmcache/cli/commands/server.py"
        require(Path(inspect.getfile(server.ServerCommand)).resolve() == expected_server, "Wrong parser import origin")
        class_file_hash = sha256(expected_server)
        receipt["server_source_sha256"] = class_file_hash
        options = set(EXPECTED) | {"--eviction-policy"}
        for name, argv in [("original", before_args), ("candidate", after_args), ("restored", before_args)]:
            stage = "PARSER_REGISTRATION"
            parser = argparse.ArgumentParser(prog="lmcache server")
            capture = RegistrationLog()
            server.logger.addHandler(capture)
            try:
                server.ServerCommand().add_arguments(parser)
            finally:
                server.logger.removeHandler(capture)
            require(not any("lmcache-cli (lightweight)" in message for message in capture.messages), "Server dependencies missing; parser registration incomplete")
            require(options <= parser._option_string_actions.keys(), "Incomplete composed parser")
            origin_receipt = {}
            for module_name in MODULES:
                module = sys.modules.get(module_name)
                require(module is not None and getattr(module, "__file__", None), "Expected real configuration module missing")
                source = Path(module.__file__).resolve()
                require(source.is_relative_to(lmcache), "Configuration module from another installation")
                origin_receipt[module_name] = {"path": str(source.relative_to(lmcache)), "sha256": sha256(source)}
            receipt["parser_source_modules"] = origin_receipt
            stage = "PARSER_COMPARISON"
            stderr = io.StringIO()
            parsed = None
            with contextlib.redirect_stderr(stderr):
                try:
                    parsed = parser.parse_args(argv)
                    code = 0
                except SystemExit as error:
                    code = error.code
            output = stderr.getvalue()
            (out / f"{name}.stderr.txt").write_text(output)
            arm = {"argv": argv, "parse_exit_code": code, "stderr": output, "registration_messages": capture.messages}
            receipt["arms"][name] = arm
            if name == "candidate":
                require(code == 0 and parsed is not None, "Candidate failed to parse")
                observed = {option: getattr(parsed, parser._option_string_actions[option].dest) for option in options}
                arm["selected_values"] = observed
                for option, value in EXPECTED.items():
                    require(observed[option] == value, f"Changed intended setting: {option}")
                require(observed["--eviction-policy"] == "LRU", "Policy not retained")
                (out / "candidate-namespace.json").write_text(json.dumps(vars(parsed), indent=2, default=str) + "\n")
            else:
                require(code == 2 and output.splitlines()[-1].endswith("the following arguments are required: --eviction-policy"), "Original not rejected for the intended missing argument")
                require("unrecognized arguments" not in output, "Wrong rejection reason")
        stage = "PROVENANCE_CHECK"
        frozen_after = subprocess.check_output([sys.executable, "-m", "pip", "freeze", "--all"], text=True)
        (out / "dependencies-after.txt").write_text(frozen_after)
        require(frozen_before == frozen_after, "Dependencies changed between comparisons")
        for root in (atom, lmcache):
            require(not git(root, "status", "--porcelain"), "Input source changed during experiment")
        receipt["dependencies_unchanged"] = True
        receipt["status"] = "REAL_PARSER_GATE_PASSED"
        receipt["limits"] = [
            "Real parser imported from pinned source with actual CPU dependencies; no parser or configuration replacements.",
            "No ServerCommand.execute call, server startup, cache allocation, model download or GPU test.",
            "Does not qualify a compiled LMCache/ROCm wheel or the running MP server.",
            "LRU is an explicit example policy, not a performance recommendation.",
        ]
        return 0
    except Exception as error:
        receipt["status"] = "BLOCKED_ENVIRONMENT" if stage in {"ENVIRONMENT_IMPORT", "PARSER_REGISTRATION"} else "EXPERIMENT_GATE_NOT_MET"
        receipt["stage"] = stage
        receipt["error_type"] = type(error).__name__
        receipt["error"] = str(error)
        (out / "exception.txt").write_text(traceback.format_exc())
        return 1
    finally:
        (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print("MP_RECIPE_RECEIPT=" + json.dumps(receipt, sort_keys=True), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
