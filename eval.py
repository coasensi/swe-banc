import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple


def run(cmd, cwd: Path, timeout: int | None = None) -> subprocess.CompletedProcess:
    """Run a command and return CompletedProcess. Raises only on unexpected OS errors."""
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        shell=False,
    )


def load_metadata(task_dir: Path, metadata_filename: str) -> dict:
    meta_path = task_dir / metadata_filename
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {meta_path}")
    return json.loads(meta_path.read_text())


def ensure_git_available() -> None:
    try:
        cp = subprocess.run(["git", "--version"], text=True, capture_output=True)
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())
    except FileNotFoundError as e:
        raise RuntimeError("git not found on PATH. Install git and restart your shell.") from e


def copy_repo_working_tree(repo_path: Path, dest: Path) -> None:
    """
    Copy repo to dest without .venv and pytest caches.
    This is simple and Windows-friendly.
    """
    ignore_names = {
        ".venv",
        ".pytest_cache",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".git",  # we'll reconstruct git by using `git -C <repo> archive` alternative below if needed
    }

    # We actually WANT the .git directory so we can checkout commits.
    # So we copy entire repo including .git, but still exclude heavy folders.
    def ignore_func(directory: str, names: list[str]) -> set[str]:
        base = os.path.basename(directory)
        ignored = set()
        for n in names:
            if n in {".venv", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache", ".tox"}:
                ignored.add(n)
        return ignored

    shutil.copytree(repo_path, dest, ignore=ignore_func, dirs_exist_ok=False)


def git_checkout(dest_repo: Path, commit: str) -> None:
    cp = run(["git", "checkout", "-f", commit], cwd=dest_repo)
    if cp.returncode != 0:
        raise RuntimeError(
            "git checkout failed.\n"
            f"STDOUT:\n{cp.stdout}\n\nSTDERR:\n{cp.stderr}"
        )

def git_clone(repo_url: str, dest_repo: Path) -> None:
    # Clone without checkout (fast, clean)
    cp = run(["git", "clone", "--no-checkout", repo_url, str(dest_repo)], cwd=dest_repo.parent)
    if cp.returncode != 0:
        raise RuntimeError(
            "git clone failed.\n"
            f"URL: {repo_url}\n\nSTDOUT:\n{cp.stdout}\n\nSTDERR:\n{cp.stderr}"
        )

    # Ensure we have all the objects we might need
    run(["git", "fetch", "--all", "--tags"], cwd=dest_repo)

    # Also fetch PR refs (GitHub), so commits only on PR branches are available
    run(["git", "fetch", "origin", "+refs/pull/*/head:refs/remotes/origin/pr/*"], cwd=dest_repo)



def apply_patch(dest_repo: Path, patch_path: Path) -> None:
    if not patch_path.exists():
        raise FileNotFoundError(f"Patch not found: {patch_path}")

    # `git apply` is robust and does not require committing.
    cp = run(["git", "apply", "--whitespace=nowarn", str(patch_path)], cwd=dest_repo)
    if cp.returncode != 0:
        raise RuntimeError(
            "Failed to apply patch with git apply.\n"
            f"Patch: {patch_path}\n\n"
            f"STDOUT:\n{cp.stdout}\n\nSTDERR:\n{cp.stderr}"
        )

def run_pytest_with_json(cwd: Path, pytest_args: list[str], timeout: int) -> Tuple[int, Dict[str, Any], str, str]:
    """
    Runs pytest with pytest-json-report enabled.
    Returns: (returncode, report_json, stdout, stderr)
    """
    report_path = cwd / ".pytest_report.json"
    if report_path.exists():
        report_path.unlink()

    cmd = [
        sys.executable, "-m", "pytest",
        "-q",
        "--json-report",
        f"--json-report-file={report_path}",
        *pytest_args,
    ]
    cp = run(cmd, cwd=cwd, timeout=timeout)

    report: Dict[str, Any] = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            report = {}

    return cp.returncode, report, cp.stdout, cp.stderr


def score_from_report(report: Dict[str, Any]) -> Tuple[float, int, int]:
    """
    Returns (score, passed, total). Score is passed/total in [0,1].
    Works even if some tests error.
    """
    summary = report.get("summary") or {}
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    errors = int(summary.get("errors", 0))
    skipped = int(summary.get("skipped", 0))

    total = passed + failed + errors + skipped
    if total <= 0:
        return 0.0, 0, 0
    return passed / total, passed, total


def main() -> None:

    parser = argparse.ArgumentParser()

    # New interface
    parser.add_argument("--task", default=None, help="Task id (folder name under tasks/), e.g. fastapi_ref_schema_regression")

    # Backward-compatible interface
    parser.add_argument("--task-dir", default=None, help="Path to the task directory containing metadata.json")
    parser.add_argument("--harness-root", default=".", help="Root folder containing tasks/ (default: .)")

    parser.add_argument("--run-visible", action="store_true", help="Also run the visible test command from metadata (not used for scoring)")
    parser.add_argument("--patch", default=None, help="Path to a unified diff patch to apply in the sandbox before running tests")
    parser.add_argument("--metadata", default="metadata.json", help="Metadata filename in task-dir (default: metadata.json)")
    args = parser.parse_args()

    harness_root = Path(args.harness_root).resolve()

    # Infer task_dir from --task if provided
    if args.task:
        inferred = harness_root / "tasks" / args.task
        args.task_dir = str(inferred)

    if not args.task_dir:
        parser.error("You must provide either --task <task_id> OR --task-dir <path>")

    task_dir = Path(args.task_dir).resolve()

    ensure_git_available()

    meta = load_metadata(task_dir, args.metadata)

    broken = meta["broken_commit"]
    timeout = int(meta.get("timeout_seconds", 600))

    # Support either repo_url (Docker/reviewer mode) or repo_path (local dev mode)
    repo_url = meta.get("repo_url")
    repo_path_str = meta.get("repo_path")
    repo_path = Path(repo_path_str).resolve() if repo_path_str else None

    hidden_rel = meta["hidden_tests_relpath"]
    hidden_tests_path = (harness_root / hidden_rel).resolve()
    if not hidden_tests_path.exists():
        raise FileNotFoundError(f"Hidden tests path not found: {hidden_tests_path}")


    # Create a fresh sandbox
    with tempfile.TemporaryDirectory(prefix="swe_sandbox_") as td:
        sandbox_repo = Path(td) / "repo"

        if repo_url:
            git_clone(repo_url, sandbox_repo)
        else:
            if repo_path is None:
                raise KeyError("metadata must define either 'repo_url' or 'repo_path'")
            copy_repo_working_tree(repo_path, sandbox_repo)

        # Ensure sandbox is at the broken commit
        git_checkout(sandbox_repo, broken)

        # Install FastAPI with its test dependencies if available
        cp = run(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-e", ".[all]"],
            cwd=sandbox_repo,
        )

        # Optional: apply agent patch
        if args.patch:
            apply_patch(sandbox_repo, Path(args.patch).resolve())

        # Optional: run visible tests (for debugging only)
        visible_out = None
        if args.run_visible and meta.get("visible_tests_cmd"):
            cmd_str = meta["visible_tests_cmd"]
            # Run through shell so we can accept the string command. Still safe because it's your local harness.
            cp = subprocess.run(cmd_str, cwd=str(sandbox_repo), text=True, encoding="utf-8", errors="replace", capture_output=True, shell=True, timeout=timeout)
            visible_out = {
                "returncode": cp.returncode,
                "stdout": cp.stdout,
                "stderr": cp.stderr,
                "cmd": cmd_str,
            }

        # Run hidden tests in the sandbox, but pointing to hidden tests directory outside the sandbox.
        # Pytest accepts absolute paths.
        rc, report, out, err = run_pytest_with_json(
            cwd=sandbox_repo,
            pytest_args=[str(hidden_tests_path)],
            timeout=timeout,
        )

        score, passed, total = score_from_report(report)
        reward = 1 if rc == 0 else 0

        result = {
            "task_id": meta.get("task_id", task_dir.name),
            "repo": repo_url if repo_url else str(repo_path),
            "broken_commit": broken,
            "reward": reward,
            "score": score,
            "passed": passed,
            "total": total,
            "pytest_returncode": rc,
        }
        if visible_out is not None:
            result["visible"] = visible_out
        if args.patch:
            result["patch"] = str(Path(args.patch).resolve())

        # Print a single JSON line (easy to log)
        print(json.dumps(result, indent=2))

        # Also print pytest output if failing (useful when debugging)
        if rc != 0:
            sys.stderr.write("\n[pytest stdout]\n" + out + "\n")
            sys.stderr.write("\n[pytest stderr]\n" + err + "\n")


if __name__ == "__main__":
    main()
