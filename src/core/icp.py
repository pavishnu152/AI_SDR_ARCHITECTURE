"""
ICP (Ideal Customer Profile) config loader.

Loads the scoring rubric from a YAML file (see configs/icp_ai_native_b2b.yaml)
into a validated Pydantic model. Kept in src/core/ rather than src/agents/
because the ICP is a cross-cutting business config — the Scoring Agent
consumes it, but the Drafting Agent (later milestone) will too, to know
which signals are worth referencing in outreach.
"""
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ICPCriterion(BaseModel):
    label: str
    weight: int = Field(..., ge=0, le=100)
    description: str


class ScoreThresholds(BaseModel):
    reject: int = Field(..., ge=0, le=100)
    review: int = Field(..., ge=0, le=100)
    ready: int = Field(..., ge=0, le=100)


class ICPConfig(BaseModel):
    name: str
    description: str
    criteria: list[ICPCriterion]
    score_thresholds: ScoreThresholds

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ICPConfig":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"ICP config not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw)

    def as_prompt_block(self) -> str:
        """
        Render the ICP as a plain-text block for injection into an agent's
        system prompt. Kept as a method here (not duplicated string
        formatting in each agent) so every agent that scores/reasons about
        ICP fit describes it identically.
        """
        lines = [f"ICP: {self.name}", self.description.strip(), "", "Weighted criteria:"]
        for c in self.criteria:
            lines.append(f"- {c.label} (weight {c.weight}): {c.description.strip()}")
        lines += [
            "",
            "Score bands (0-100):",
            f"- 0-{self.score_thresholds.reject}: weak/no fit, reject",
            (
                f"- {self.score_thresholds.reject + 1}-{self.score_thresholds.review}: "
                f"borderline, needs human review"
            ),
            f"- {self.score_thresholds.review + 1}-100: strong fit, ready for outreach",
        ]
        return "\n".join(lines)

    def band_for_score(self, score: int) -> str:
        """
        Maps a raw 0-100 score to its band ("reject" / "review" / "ready")
        using this ICP's thresholds. Single source of truth for the
        reject/review/ready boundary — used by the eval harness
        (src/eval/run_eval.py) to grade the Scoring Agent's output. The
        orchestrator's reject-early gate currently inlines the reject
        boundary directly (`score <= icp.score_thresholds.reject`); this
        method exists for the eval harness's 3-way classification, but
        would be a reasonable minor refactor to route the orchestrator
        through as well for a single source of truth.
        """
        if score <= self.score_thresholds.reject:
            return "reject"
        if score <= self.score_thresholds.review:
            return "review"
        return "ready"


@lru_cache
def get_icp_config(path: str | None = None) -> ICPConfig:
    """
    Cached loader — parses the YAML once per process. Pass an explicit path
    in tests to load a fixture config without touching the real one; falls
    back to settings.icp_config_path otherwise.
    """
    if path is None:
        from src.core.config import get_settings

        path = get_settings().icp_config_path
    return ICPConfig.from_yaml(path)
