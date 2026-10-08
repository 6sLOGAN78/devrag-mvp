"""Composite model ids ``model@instance@provider`` (LLM-15, D-18).

``model@provider`` is the canonical form for the ``default`` instance; the 3-part form names another instance.
Model names may contain ``/`` and ``:`` (``baai/bge-m3``, ``qwen3:8b``) but never ``@``, whitespace or control characters.

A composite id is stored in ``tenant.llm_id``, ``tenant.embd_id`` and ``knowledgebase.embd_id``, all ``VARCHAR(128)``,
so the whole string is bounded by ``MAX_COMPOSITE_LENGTH`` in addition to the per-part bound. Errors carry a fixed message
and never echo the input. This module imports nothing from api, rag or quart.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_INSTANCE = "default"
MAX_PART_LENGTH = 128
MAX_COMPOSITE_LENGTH = 128
_SEPARATOR = "@"
_INVALID = "invalid model reference"


class InvalidModelRef(ValueError):
    """The value is not a valid composite model id. The message is fixed and never contains the input."""


@dataclass(frozen=True)
class ModelRef:
    model: str
    instance: str
    provider: str

    @property
    def composite(self) -> str:
        return format_model_ref(self.model, self.provider, self.instance)


def _check_part(part: object) -> str:
    if not isinstance(part, str) or not part or len(part) > MAX_PART_LENGTH:
        raise InvalidModelRef(_INVALID)
    if _SEPARATOR in part or any(ch.isspace() or not ch.isprintable() for ch in part):
        raise InvalidModelRef(_INVALID)
    return part


def _join(model: str, provider: str, instance: str) -> str:
    composite = f"{model}{_SEPARATOR}{provider}" if instance == DEFAULT_INSTANCE else f"{model}{_SEPARATOR}{instance}{_SEPARATOR}{provider}"
    if len(composite) > MAX_COMPOSITE_LENGTH:
        raise InvalidModelRef(_INVALID)
    return composite


def parse_model_ref(value: str) -> ModelRef:
    """Split ``model@provider`` or ``model@instance@provider``; anything else raises ``InvalidModelRef``."""
    if not isinstance(value, str) or len(value) > MAX_COMPOSITE_LENGTH:
        raise InvalidModelRef(_INVALID)
    parts = value.split(_SEPARATOR)
    if len(parts) == 2:
        model, provider = parts
        instance = DEFAULT_INSTANCE
    elif len(parts) == 3:
        model, instance, provider = parts
    else:
        raise InvalidModelRef(_INVALID)
    return ModelRef(_check_part(model), _check_part(instance), _check_part(provider))


def format_model_ref(model: str, provider: str, instance: str = DEFAULT_INSTANCE) -> str:
    """Compose the canonical id: 2-part for the default instance, 3-part otherwise."""
    return _join(_check_part(model), _check_part(provider), _check_part(instance))
