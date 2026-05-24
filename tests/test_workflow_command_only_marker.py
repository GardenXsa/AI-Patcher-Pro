"""Regression marker for command-only patches.

AI Patcher Pro must support patches with operations=[] and commands=[...].
This file exists mostly as a stable marker so command-only verification patches
are never sent without a file operation again.
"""


def test_command_only_marker_exists():
    assert True
