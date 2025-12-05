"""Pytest fixtures for Exocortex tests."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from exocortex.config import Config, reset_config
from exocortex.container import Container, reset_container


@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_config(temp_data_dir: Path) -> Generator[Config, None, None]:
    """Create a test configuration."""
    config = Config(
        data_dir=temp_data_dir,
        db_name="test_db",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        link_suggestion_threshold=0.65,
        duplicate_detection_threshold=0.90,
        contradiction_check_threshold=0.70,
        max_summary_length=200,
        max_tags_per_memory=20,
        stale_memory_days=90,
    )
    yield config


@pytest.fixture
def container(test_config: Config) -> Generator[Container, None, None]:
    """Create a test container with isolated dependencies."""
    # Reset any global state
    reset_config()
    reset_container()

    # Create container with test config
    container = Container.create(test_config)
    yield container

    # Cleanup
    container.close()
    reset_container()
    reset_config()


@pytest.fixture(autouse=True)
def set_test_env(temp_data_dir: Path) -> Generator[None, None, None]:
    """Set environment variables for tests."""
    old_env = os.environ.get("EXOCORTEX_DATA_DIR")
    os.environ["EXOCORTEX_DATA_DIR"] = str(temp_data_dir)
    yield
    if old_env:
        os.environ["EXOCORTEX_DATA_DIR"] = old_env
    else:
        os.environ.pop("EXOCORTEX_DATA_DIR", None)
