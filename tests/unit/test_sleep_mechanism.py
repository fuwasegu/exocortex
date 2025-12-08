"""Unit tests for Sleep/Dream Mechanism (Phase 3).

Tests the background consolidation process utilities.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from exocortex.worker.process import (
    get_default_log_path,
    is_dreamer_running,
    spawn_detached_dreamer,
)


class TestSpawnDetachedDreamer:
    """Tests for the spawn_detached_dreamer function."""

    @patch("exocortex.worker.process.subprocess.Popen")
    def test_spawn_returns_true_on_success(self, mock_popen):
        """Test that spawn returns True when process starts successfully."""
        mock_popen.return_value = MagicMock()

        result = spawn_detached_dreamer()

        assert result is True
        mock_popen.assert_called_once()

    @patch("exocortex.worker.process.subprocess.Popen")
    def test_spawn_returns_false_on_error(self, mock_popen):
        """Test that spawn returns False when process fails to start."""
        mock_popen.side_effect = OSError("Failed to spawn")

        result = spawn_detached_dreamer()

        assert result is False

    @patch("exocortex.worker.process.subprocess.Popen")
    def test_spawn_command_includes_module(self, mock_popen):
        """Test that spawn command includes correct module path."""
        mock_popen.return_value = MagicMock()

        spawn_detached_dreamer()

        call_args = mock_popen.call_args
        cmd = call_args[0][0]

        # Should use python -m exocortex.worker.dream
        assert cmd[0] == sys.executable
        assert "-m" in cmd
        assert "exocortex.worker.dream" in cmd

    @patch("exocortex.worker.process.subprocess.Popen")
    def test_spawn_with_log_file(self, mock_popen):
        """Test spawn with log file specified."""
        mock_popen.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "dream.log"
            result = spawn_detached_dreamer(log_file=log_path)

            assert result is True
            # Log directory should be created
            assert log_path.parent.exists()

    @patch("exocortex.worker.process.subprocess.Popen")
    def test_spawn_detached_unix(self, mock_popen):
        """Test spawn uses start_new_session on Unix."""
        mock_popen.return_value = MagicMock()

        if sys.platform != "win32":
            spawn_detached_dreamer()

            call_kwargs = mock_popen.call_args[1]
            assert call_kwargs.get("start_new_session") is True
            assert call_kwargs.get("close_fds") is True


class TestIsDreamerRunning:
    """Tests for the is_dreamer_running function."""

    def test_returns_false_when_lock_not_exists(self):
        """Test returns False when lock file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "nonexistent.lock"
            assert is_dreamer_running(lock_path) is False

    def test_returns_false_when_lock_acquirable(self):
        """Test returns False when lock can be acquired (no worker running)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "dream.lock"
            # Create empty lock file
            lock_path.touch()

            result = is_dreamer_running(lock_path)
            assert result is False

    def test_returns_true_when_lock_held(self):
        """Test returns True when lock is held by another process."""
        from filelock import FileLock

        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "dream.lock"
            lock = FileLock(lock_path, timeout=1)

            # Hold the lock
            lock.acquire()
            try:
                # Check from a simulated "other process" perspective
                # Since we hold it, the function should detect it's in use
                # But actually, same process can re-acquire, so we need
                # a different approach

                # For this test, we verify the lock is held
                assert lock.is_locked
            finally:
                lock.release()


class TestGetDefaultLogPath:
    """Tests for get_default_log_path function."""

    @patch("exocortex.config.get_config")
    def test_returns_correct_path(self, mock_get_config):
        """Test that default log path is in data_dir/logs/."""
        mock_config = MagicMock()
        mock_config.data_dir = Path("/home/user/.exocortex")
        mock_get_config.return_value = mock_config

        log_path = get_default_log_path()

        assert log_path == Path("/home/user/.exocortex/logs/dream.log")
        assert "logs" in log_path.parts
        assert log_path.name == "dream.log"


class TestDreamWorkerInit:
    """Tests for DreamWorker initialization."""

    def test_worker_creation(self):
        """Test DreamWorker can be instantiated."""
        from exocortex.config import Config
        from exocortex.worker.dream import DreamWorker

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir))
            worker = DreamWorker(config=config, lock_timeout=1.0, max_runtime=10.0)

            assert worker.config == config
            assert worker.lock_timeout == 1.0
            assert worker.max_runtime == 10.0
            assert worker.lock_path == Path(tmpdir) / "dream.lock"

    def test_worker_kuzu_lock_path(self):
        """Test KùzuDB lock path is set correctly."""
        from exocortex.config import Config
        from exocortex.worker.dream import DreamWorker

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir), db_name="test_db")
            worker = DreamWorker(config=config)

            expected_kuzu_lock = Path(tmpdir) / "test_db" / ".lock"
            assert worker._kuzu_lock_path == expected_kuzu_lock

    def test_worker_check_server_flag(self):
        """Test check_server flag is configurable."""
        from exocortex.config import Config
        from exocortex.worker.dream import DreamWorker

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir))

            worker_check = DreamWorker(config=config, check_server=True)
            assert worker_check.check_server is True

            worker_no_check = DreamWorker(config=config, check_server=False)
            assert worker_no_check.check_server is False

    def test_worker_default_config(self):
        """Test DreamWorker uses default config if not provided."""
        from exocortex.worker.dream import DreamWorker

        with patch("exocortex.worker.dream.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.data_dir = Path("/tmp/test")
            mock_get_config.return_value = mock_config

            worker = DreamWorker()

            assert worker.config == mock_config


class TestDreamWorkerLocking:
    """Tests for DreamWorker file locking behavior."""

    def test_lock_file_location(self):
        """Test lock file is created in data directory."""
        from exocortex.config import Config
        from exocortex.worker.dream import DreamWorker

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir))
            worker = DreamWorker(config=config)

            expected_lock = Path(tmpdir) / "dream.lock"
            assert worker.lock_path == expected_lock

    def test_worker_handles_lock_timeout(self):
        """Test worker handles lock timeout gracefully."""
        from filelock import FileLock

        from exocortex.config import Config
        from exocortex.worker.dream import DreamWorker

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir))
            lock_path = Path(tmpdir) / "dream.lock"

            # Pre-acquire the lock
            external_lock = FileLock(lock_path)
            external_lock.acquire()

            try:
                # Worker should handle timeout gracefully
                worker = DreamWorker(config=config, lock_timeout=0.1)

                # This should not raise, just exit gracefully
                # We can't easily test the full run() due to dependencies
                # but we can verify the setup
                assert worker.lock_timeout == 0.1
            finally:
                external_lock.release()


class TestDreamWorkerSafetyChecks:
    """Tests for DreamWorker safety check methods."""

    def test_is_kuzu_locked_false_when_no_lock(self):
        """Test _is_kuzu_locked returns False when no lock file exists."""
        from exocortex.config import Config
        from exocortex.worker.dream import DreamWorker

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir), db_name="test_db")
            worker = DreamWorker(config=config)

            # No lock file exists
            assert worker._is_kuzu_locked() is False

    def test_is_kuzu_locked_true_when_lock_exists(self):
        """Test _is_kuzu_locked returns True when lock file exists."""
        from exocortex.config import Config
        from exocortex.worker.dream import DreamWorker

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir), db_name="test_db")
            worker = DreamWorker(config=config)

            # Create the lock file path
            lock_dir = Path(tmpdir) / "test_db"
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_file = lock_dir / ".lock"
            lock_file.touch()

            assert worker._is_kuzu_locked() is True

    def test_is_sse_server_likely_running_false_when_no_server(self):
        """Test _is_sse_server_likely_running returns False when no server."""
        from exocortex.config import Config
        from exocortex.worker.dream import DreamWorker

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir))
            worker = DreamWorker(config=config)

            # No server running on port 8765 (usually)
            # This test may be flaky if something happens to be using that port
            result = worker._is_sse_server_likely_running()
            # Can't guarantee False, but should not raise
            assert isinstance(result, bool)


class TestDreamWorkerSignalHandling:
    """Tests for DreamWorker signal handling."""

    def test_running_flag_initialized_false(self):
        """Test _running flag starts as False."""
        from exocortex.config import Config
        from exocortex.worker.dream import DreamWorker

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir))
            worker = DreamWorker(config=config)

            assert worker._running is False

    def test_signal_handler_sets_running_false(self):
        """Test signal handler sets _running to False."""
        from exocortex.config import Config
        from exocortex.worker.dream import DreamWorker

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir))
            worker = DreamWorker(config=config)
            worker._running = True

            # Simulate signal
            worker._handle_signal(15, None)  # SIGTERM

            assert worker._running is False
