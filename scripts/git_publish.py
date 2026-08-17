from __future__ import annotations

from pathlib import Path
import subprocess


class RemoteSyncError(RuntimeError):
    """Raised when publishing cannot safely synchronize with the remote branch."""


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def is_non_fast_forward_error(error: subprocess.CalledProcessError) -> bool:
    message = f"{error.stdout or ''}\n{error.stderr or ''}".lower()
    return "fetch first" in message or "non-fast-forward" in message


def sync_remote_preserving(
    repo: Path,
    publish_files: list[str],
    remote: str = "origin",
    branch: str = "main",
) -> None:
    """Merge the remote branch while keeping the just-built publish artifacts.

    Only conflicts in ``publish_files`` are resolved automatically. Any code or
    configuration conflict aborts the merge so the import tool cannot silently
    overwrite work from another computer.
    """

    preserved = {
        relative: (repo / relative).read_bytes()
        for relative in publish_files
        if (repo / relative).exists()
    }
    allowed = {Path(relative).as_posix() for relative in publish_files}

    run_git(repo, "fetch", remote, branch)
    remote_ref = f"{remote}/{branch}"
    ancestor = run_git(
        repo, "merge-base", "--is-ancestor", remote_ref, "HEAD", check=False
    )
    if ancestor.returncode == 0:
        return

    merge = run_git(
        repo, "merge", "--no-commit", "--no-edit", remote_ref, check=False
    )
    conflicts = {
        Path(item).as_posix()
        for item in run_git(
            repo, "diff", "--name-only", "--diff-filter=U", check=False
        ).stdout.splitlines()
        if item.strip()
    }
    unexpected = conflicts - allowed
    if merge.returncode != 0 and (not conflicts or unexpected):
        merge_head = run_git(
            repo, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False
        )
        if merge_head.returncode == 0:
            run_git(repo, "merge", "--abort", check=False)
        details = (merge.stderr or merge.stdout or "Git merge failed").strip()
        if unexpected:
            details += "\nXung đột ngoài snapshot: " + ", ".join(sorted(unexpected))
        raise RemoteSyncError(details)

    for relative, content in preserved.items():
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    run_git(repo, "add", *publish_files)

    merge_head = run_git(
        repo, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False
    )
    if merge_head.returncode == 0:
        run_git(repo, "commit", "-m", f"Merge {remote_ref} before publishing snapshot")


def push_with_remote_sync(
    repo: Path,
    publish_files: list[str],
    remote: str = "origin",
    branch: str = "main",
) -> None:
    """Synchronize then push, retrying once if another publisher wins the race."""

    for attempt in range(2):
        sync_remote_preserving(repo, publish_files, remote=remote, branch=branch)
        try:
            run_git(repo, "push", remote, branch)
            return
        except subprocess.CalledProcessError as error:
            if attempt == 0 and is_non_fast_forward_error(error):
                continue
            raise

