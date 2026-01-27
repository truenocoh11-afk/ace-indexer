# Antigravity Context Engine (ACE) - Portable Edition 🚀

ACE is a lightweight, local "Sidecar" that powers your AI Agents (Gemini, Claude, Open Code) with deep code understanding.
It creates a **Search Engine** for your code, running entirely on your machine.

## ✨ Features
*   **Hybrid RAG**: Combines Semantic Search (Vectors) with Keyword Search.
*   **Skeletonization**: Reads code structure (Classes/Funcs) without waisting tokens on implementation details.
*   **Portable**: Just copy this folder anywhere.
*   **Zero-Config**: Indices are stored locally in each project's `.ace` folder.

## 📦 Installation
1.  **Requirements**: Windows, Python 3.10+ installed.
2.  **Setup**:
    Double-click `setup.bat` to recreate the environment.
3.  **Start**:
    Double-click `start.bat` to run the server. keep this window open!

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
*   `ace_search_code(query, project_path)`: Finds code relevant to your question.
*   `ace_read_skeleton(file_path)`: Reads the "shape" of a file to save tokens.
*   `ace_index_project(project_path)`: Forces a re-scan.

## 📂 Data Storage
ACE stores its index hidden inside your project folder:
`YourProject/.ace/`

> **Note**: This folder contains a `.gitignore` to prevent it from being uploaded to GitHub.
