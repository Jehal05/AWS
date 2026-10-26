from __future__ import annotations

from ..config import Settings
from .base import ChatModel
from .mock import MockModel


def build_model(settings: Settings) -> ChatModel:
    if settings.model == "mock":
        return MockModel()
    if settings.model == "bedrock":
        raise NotImplementedError("The Bedrock model adapter arrives in the AWS integration step.")
    raise ValueError(f"unknown RENEWFLOW_MODEL: {settings.model!r}")
