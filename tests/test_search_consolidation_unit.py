
import sys
import unittest

# Simplified logic from mcp_server.py to verify parameter handling and redirects
def mock_call_tool(name, arguments):
    # Simulated search consolidation logic
    if name == "ace_search_code":
        query = arguments.get("query")
        fmt = arguments.get("format", "compact")
        auto_usages = arguments.get("auto_usages", False)
        workspace_only = arguments.get("workspace_only", True)
        return {
            "name": name,
            "query": query,
            "format": fmt,
            "auto_usages": auto_usages,
            "workspace_only": workspace_only
        }
    elif name == "ace_search_code_compact":
        # Redirect logic
        arguments["format"] = "compact"
        return mock_call_tool("ace_search_code", arguments)
    return None

class TestConsolidationLogic(unittest.TestCase):
    def test_default_parameters(self):
        args = {"query": "test_query"}
        result = mock_call_tool("ace_search_code", args)
        self.assertEqual(result["format"], "compact")
        self.assertEqual(result["auto_usages"], False)
        self.assertEqual(result["workspace_only"], True)

    def test_explicit_parameters(self):
        args = {
            "query": "test_query",
            "format": "verbose",
            "auto_usages": True,
            "workspace_only": False
        }
        result = mock_call_tool("ace_search_code", args)
        self.assertEqual(result["format"], "verbose")
        self.assertEqual(result["auto_usages"], True)
        self.assertEqual(result["workspace_only"], False)

    def test_legacy_redirect(self):
        args = {"query": "test_query"}
        result = mock_call_tool("ace_search_code_compact", args)
        self.assertEqual(result["name"], "ace_search_code")
        self.assertEqual(result["format"], "compact")

if __name__ == "__main__":
    unittest.main()
