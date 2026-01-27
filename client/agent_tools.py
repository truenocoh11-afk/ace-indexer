import requests
import json
import os

ACE_URL = "http://localhost:8000/v1/context/query"

def search_code(query: str, project_path: str = None):
    """
    Tools for Agents to query the ACE Server.
    """
    if not project_path:
        project_path = os.getcwd() # Assumption: Agent runs in project root

    try:
        response = requests.post(
            ACE_URL,
            json={"query": query},
            headers={"X-Project-Path": project_path},
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        else:
            return f"Error talking to ACE: {response.text}"
    except Exception as e:
        return f"ACE Server unreachable. Is it running? Error: {e}"

if __name__ == "__main__":
    # Test
    print(search_code("test query", project_path="C:/Test/Project"))
