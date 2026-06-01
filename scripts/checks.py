# -*- coding: utf-8 -*-
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_FILES = [
    "main.py",
    "server.py",
    "src/agent.py",
    "src/cost.py",
    "src/evaluate.py",
    "src/generator.py",
    "src/loader.py",
    "src/retriever.py",
    "src/schema.py",
    "src/tools.py",
    "src/tracing.py",
    "tests/test_agent.py",
]


def run_step(name: str, command: list[str]) -> None:
    print(f"\n==> {name}", flush=True)
    print(" ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    run_step(
        "Python syntax check",
        [sys.executable, "-B", "-m", "py_compile", *PYTHON_FILES],
    )
    run_step(
        "Unit tests",
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
    )
    run_step(
        "Evaluation smoke test",
        [
            sys.executable,
            "-B",
            "-m",
            "src.evaluate",
            "--no-persist-traces",
            "--local-only",
        ],
    )
    if shutil.which("node"):
        run_step("Frontend JavaScript syntax check", ["node", "--check", "frontend/app.js"])
    else:
        print("\n==> Frontend JavaScript syntax check")
        print("Skipped because node is not installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
