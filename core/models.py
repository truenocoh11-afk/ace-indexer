from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class ContextQuery(BaseModel):
    query: str
    limit: int = 5
    strategy: Literal["hybrid", "semantic", "keyword"] = "hybrid"

class ContextResult(BaseModel):
    file_path: str
    relevance: float
    content: str
    type: Literal["skeleton", "snippet", "full"]

class IndexRequest(BaseModel):
    project_path: str
    force: bool = False
