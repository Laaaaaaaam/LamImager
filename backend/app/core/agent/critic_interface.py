from dataclasses import dataclass, field


@dataclass
class CriticOutput:
    artifact_id: str
    score: float
    tags: dict = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
