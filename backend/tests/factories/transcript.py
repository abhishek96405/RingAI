"""Transcript factory — builds a minimal turn-by-turn conversation."""
from __future__ import annotations

from typing import Any


def make_transcript(**overrides: Any) -> list[dict]:
    """Return a list of conversation turns. Default is a simple pickup order."""
    turns = [
        {"role": "assistant", "text": "Hi, thanks for calling. How can I help?"},
        {"role": "user", "text": "I'd like to order a Margherita Pizza for pickup."},
        {"role": "assistant", "text": "One Margherita Pizza for pickup, anything else?"},
        {"role": "user", "text": "That's all, thanks."},
        {"role": "assistant", "text": "Your total is $14.99. See you soon!"},
    ]
    if "turns" in overrides:
        return overrides["turns"]
    return turns
