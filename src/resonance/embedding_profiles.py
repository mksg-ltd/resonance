"""Bundled embedding model catalog and profile lookup."""

from functools import cache
from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class EmbeddingProfile(BaseModel):
    """A supported model and the request protocol used to reach it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str = Field(min_length=1)
    dimensions: int = Field(gt=0)
    protocol: Literal["openai-compatible", "ollama"]
    revision: str | None = None


@cache
def embedding_profiles() -> dict[str, EmbeddingProfile]:
    """Read the application-shipped profile catalog, including from wheels."""
    catalog_path = files("resonance").joinpath("data/embedding_profiles.yaml")
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
        msg = "Bundled embedding profile catalog is invalid"
        raise TypeError(msg)
    return {name: EmbeddingProfile.model_validate(profile) for name, profile in data["profiles"].items()}


def get_embedding_profile(profile_id: str) -> EmbeddingProfile:
    """Return a profile by stable ID or report the supported IDs."""
    profiles = embedding_profiles()
    profile = profiles.get(profile_id)
    if profile is None:
        available = ", ".join(sorted(profiles))
        msg = f"Unknown embedding profile '{profile_id}'. Supported profiles: {available}"
        raise ValueError(msg)
    return profile
