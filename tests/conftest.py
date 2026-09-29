"""Rules for every app test run.

A skipped or expected-to-fail test fails the run. A test that doesn't run proves
nothing, so it gets fixed, or the owner decides (see .claude/skills/testing).
"""

import pytest


def pytest_sessionfinish(session: pytest.Session) -> None:
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    not_run = {
        kind: len(reporter.stats[kind])
        for kind in ("skipped", "xfailed")
        if reporter.stats.get(kind)
    }
    if not_run:
        reporter.write_line(f"Tests that didn't run count as failures: {not_run}", red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
