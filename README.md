# Antigravity Context Engine (ACE) - Portable Edition 🚀

ACE is a lightweight, local "Sidecar" that powers your AI Agents (Gemini, Claude, Open Code) with deep code understanding.
It creates a **Search Engine** for your code, running entirely on your machine.

**Current Version**: v1.2.0 (Phase 3: Advanced Intelligence)

## ✨ Features
*   **Hybrid RAG**: Combines Semantic Search (Vectors) with Keyword Search.
*   **Skeletonization**: Reads code structure (Classes/Funcs) without wasting tokens on implementation details.
*   **Call Graphs & Markov**: Analyzes call frequencies and generates Mermaid diagrams.
*   **Inheritance Tracing**: Deeply understands class hierarchies via AST.
*   **Zero-Config**: Indices are stored locally in each project's `.ace` folder.

## 📦 Installation
1.  **Requirements**: Windows, Python 3.10+ installed.
2.  **Setup**:
    Double-click `setup.bat` to recreate the environment.
3.  **Start**:
    Double-click `start.bat` to run the server. Keep this window open!

## 🔌 Integration (MCP)
ACE uses the **Model Context Protocol (MCP)**. You can add it to any compatible IDE or Agent.

### For Antigravity / Claude Desktop
Add this to your MCP Configuration file:

```json
{
  "mcpServers": {
    "ace": {
      "command": "cmd.exe",
      "args": [
        "/c",
        "C:\\ABSOLUTE\\PATH\\TO\\ace_engine\\run_mcp.bat"
      ]
    }
  }
}
```
*(Replace the path with the location where you put this folder)*

## 🛠 Usage
Once connected, your Agent will have access to these tools:
*   `ace_search_code_compact`: High-density search (recommended).
*   `ace_call_graph`: Generates call graphs and dependency visualizations.
*   `ace_get_symbol`: Direct retrieval of function/class logic.
*   `ace_manage_index`: Unified tool for status, listing, and reindexing.

## 📂 Data Storage
ACE stores its index hidden inside your project folder:
`YourProject/.ace/`

> **Note**: This folder contains a `.gitignore` to prevent it from being uploaded to GitHub.
