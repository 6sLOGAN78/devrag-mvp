"""Model metadata registry (plan 03-05, LLM-22).

Context sizes and list prices for the models devRag seeds or documents. Prices are US dollars per one million tokens and are
informational (usage display), never used for billing. Unknown models get a conservative default so callers never need to
special-case a missing entry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelMeta:
    max_tokens: int
    max_completion_tokens: int
    is_vision: bool
    input_price: float
    output_price: float


DEFAULT_META = ModelMeta(max_tokens=8192, max_completion_tokens=4096, is_vision=False, input_price=0.0, output_price=0.0)

_SEEDED: dict[str, ModelMeta] = {
    "meta-llama/llama-3.1-8b-instruct": ModelMeta(131072, 16384, False, 0.05, 0.08),
    "baai/bge-m3": ModelMeta(8194, 0, False, 0.01, 0.0),
    "openai/text-embedding-3-small": ModelMeta(8192, 0, False, 0.02, 0.0),
    "text-embedding-3-small": ModelMeta(8192, 0, False, 0.02, 0.0),
    "mistralai/mistral-nemo": ModelMeta(131072, 16384, False, 0.02, 0.04),
    "gpt-4o-mini": ModelMeta(128000, 16384, True, 0.15, 0.60),
    "openai/gpt-4o-mini": ModelMeta(128000, 16384, True, 0.15, 0.60),
}

# o1 / o3 / o4 families (LLM-18): optionally prefixed by a vendor segment, then the family, then "-suffix" or end.
REASONING_MODEL = re.compile(r"^(?:.*/)?(o1|o3|o4)(?:-|$)")


def lookup(provider: str, model: str) -> ModelMeta:
    """Metadata for ``model``; the provider is accepted so a later per-provider override needs no signature change."""
    del provider
    return _SEEDED.get(model.strip().lower(), DEFAULT_META)
