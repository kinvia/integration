"""Tests for repair registry reconciliation."""

from kinvia.repair_sync import diff_repair_snapshots


def test_diff_repair_snapshots_detects_removed():
    previous = {("spook", "issue_a"), ("spook", "issue_b")}
    current = {("spook", "issue_a")}
    added, removed = diff_repair_snapshots(previous, current)
    assert added == set()
    assert removed == {("spook", "issue_b")}


def test_diff_repair_snapshots_detects_added():
    previous = {("spook", "issue_a")}
    current = {("spook", "issue_a"), ("homeassistant", "issue_b")}
    added, removed = diff_repair_snapshots(previous, current)
    assert added == {("homeassistant", "issue_b")}
    assert removed == set()
