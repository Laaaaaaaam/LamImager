from pydantic import BaseModel


class PromptOptimizeRequest(BaseModel):
    prompt: str
    direction: str
    llm_provider_id: str


class PromptOptimizeResponse(BaseModel):
    original: str
    optimized: str
    direction: str
