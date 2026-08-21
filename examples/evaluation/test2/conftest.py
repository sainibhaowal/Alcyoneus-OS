"""Shared fixtures for test2 — all-criteria single-turn tests."""

import pytest

from ..test_graph import create_app_and_collector


@pytest.fixture(scope="session")
def trajectory_app():
    """Compile once per test session — shared across all tests."""
    return create_app_and_collector()


@pytest.fixture(scope="session")
def compiled_graph(trajectory_app):
    return trajectory_app[0]


@pytest.fixture(scope="session")
def collector(trajectory_app):
    return trajectory_app[1]
