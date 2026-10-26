from __future__ import annotations

from ..config import Settings
from .base import ChatModel
from .mock import MockModel


def build_model(settings: Settings) -> ChatModel:
    if settings.model == "mock":
        return MockModel()
    if settings.model == "bedrock":
        import boto3  # imported lazily so local mode never needs it

        from .bedrock import BedrockModel

        client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        return BedrockModel(client, settings.bedrock_model_id)
    raise ValueError(f"unknown RENEWFLOW_MODEL: {settings.model!r}")
