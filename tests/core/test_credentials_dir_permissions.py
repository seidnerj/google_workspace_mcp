"""Regression tests for check_credentials_directory_permissions.

The original implementation branched on os.path.exists, wrote a SHARED
'.permission_test' filename, and on failure removed the directory with
os.rmdir. When multiple MCP server processes (e.g. the personal and work
google-workspace servers Claude Code launches together) initialize the SAME
~/.google_workspace_mcp/credentials directory concurrently, those steps race:
one process's cleanup/remove yanks the dir or the shared probe file out from
under a sibling, whose write then fails with ENOENT and crashes startup
("Connection closed" -> server shows as failed). These tests pin the
concurrency-safe, non-destructive behavior.
"""

import os
import threading

from core.utils import check_credentials_directory_permissions


def test_concurrent_checks_on_shared_dir_all_succeed(tmp_path):
    """Many processes initializing the same (initially missing) credentials dir
    at once must all succeed -- reproduces the startup race."""
    target = str(tmp_path / "credentials")  # does not exist yet
    errors: list[str] = []
    n = 24
    barrier = threading.Barrier(n)

    def worker():
        try:
            barrier.wait()
            for _ in range(5):
                check_credentials_directory_permissions(target)
        except Exception as e:  # noqa: BLE001 - capture for assertion
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"{len(errors)} concurrent failures, e.g. {errors[:3]}"
    assert os.path.isdir(target)


def test_check_preserves_existing_dir_and_contents(tmp_path):
    """The check must never delete the credentials dir or its contents, and must
    not leave probe files behind."""
    target = tmp_path / "credentials"
    target.mkdir()
    keep = target / "token.json"
    keep.write_text("secret")

    check_credentials_directory_permissions(str(target))

    assert target.is_dir()
    assert keep.read_text() == "secret"
    assert not list(target.glob(".permission_test*"))


def test_check_creates_missing_dir(tmp_path):
    target = tmp_path / "nested" / "credentials"
    check_credentials_directory_permissions(str(target))
    assert target.is_dir()
