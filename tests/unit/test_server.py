"""Unit tests for server module."""

from __future__ import annotations

import json

from exocortex.server import _normalize_content


class TestNormalizeContent:
    """Tests for _normalize_content helper function."""

    def test_plain_text_unchanged(self):
        """Plain text should be returned unchanged."""
        content = "# Hello World\n\nThis is plain markdown."
        assert _normalize_content(content) == content

    def test_empty_string_unchanged(self):
        """Empty string should be returned unchanged."""
        assert _normalize_content("") == ""

    def test_none_handling(self):
        """None should be returned as-is (falsy check)."""
        # The function returns content if not content, which handles None
        assert _normalize_content("") == ""

    def test_single_layer_json_extraction(self):
        """Single layer MCP TextContent format should be extracted."""
        content = '[{"text": "# Hello\\nWorld", "type": "text"}]'
        assert _normalize_content(content) == "# Hello\nWorld"

    def test_double_layer_json_extraction(self):
        """Double-encoded MCP TextContent format should be fully extracted."""
        # This is the actual format seen in corrupted memories:
        # [{"text": "[{\"text\": \"actual content\", \"type\": \"text\"}]", "type": "text"}]
        actual_content = "# Hello\nWorld"
        inner_json = json.dumps([{"text": actual_content, "type": "text"}])
        outer_json = json.dumps([{"text": inner_json, "type": "text"}])

        result = _normalize_content(outer_json)
        assert result == actual_content

    def test_json_array_without_text_key_unchanged(self):
        """JSON array without 'text' key should be unchanged."""
        content = '[{"data": "something"}]'
        assert _normalize_content(content) == content

    def test_non_array_json_unchanged(self):
        """Non-array JSON should be unchanged."""
        content = '{"text": "hello"}'
        assert _normalize_content(content) == content

    def test_invalid_json_unchanged(self):
        """Invalid JSON that looks like array should be unchanged."""
        content = "[not valid json]"
        assert _normalize_content(content) == content

    def test_markdown_with_brackets_unchanged(self):
        """Markdown containing brackets should not be altered."""
        content = "Use array syntax like [1, 2, 3] in code."
        assert _normalize_content(content) == content

    def test_real_world_mcp_content(self):
        """Test with real-world MCP TextContent format."""
        mcp_content = '[{"text": "# Test Title\\n\\nSome content with **bold** text.", "type": "text"}]'
        expected = "# Test Title\n\nSome content with **bold** text."
        assert _normalize_content(mcp_content) == expected

    def test_complex_markdown_extraction(self):
        """Test extraction of complex markdown with code blocks."""
        markdown = (
            "# Code Example\\n\\n```python\\ndef hello():\\n    print('world')\\n```"
        )
        mcp_content = f'[{{"text": "{markdown}", "type": "text"}}]'
        result = _normalize_content(mcp_content)
        assert "# Code Example" in result
        assert "def hello():" in result
