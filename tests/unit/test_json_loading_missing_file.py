"""
Unit tests for JsonLoadingUtility missing file handling.
"""

import pytest
from unittest.mock import patch

from cdk_factory.utilities.json_loading_utility import JsonLoadingUtility


class TestJsonLoadingMissingFile:
    """Test JsonLoadingUtility missing file error handling."""

    @patch("os.path.exists", return_value=False)
    def test_missing_file_exits(self, mock_exists):
        """Verify sys.exit(1) is called for missing file."""
        loader = JsonLoadingUtility("/nonexistent/config.json")
        with pytest.raises(SystemExit) as exc_info:
            loader.load()
        assert exc_info.value.code == 1

    @patch("os.path.exists", return_value=False)
    def test_missing_file_prints_path(self, mock_exists, capsys):
        """Verify error message includes the missing file path."""
        loader = JsonLoadingUtility("/nonexistent/config.json")
        with pytest.raises(SystemExit):
            loader.load()
        captured = capsys.readouterr()
        assert "/nonexistent/config.json" in captured.out
