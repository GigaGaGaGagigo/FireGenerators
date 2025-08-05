"""
WRITER: Kang Joseph
DATE: 2025-08-01
DESCRIPTION:
This module provides a factory function to create and cache LLM clients.

It supports the following models:
- gemini-2.5-flash

TODO: Add support for other models.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

ENV_PATH: Path = Path(__file__).parent.parent.parent.parent.parent / ".env"
GEMINI_MODEL_NAME: str = "gemini-2.5-flash"

load_dotenv(ENV_PATH)

_llm_agents = {}
api_key: str | None = os.getenv("GEMINI_API_KEY")


def get_llm_agents(model_name: str):
    if model_name in _llm_agents:
        return _llm_agents[model_name]

    # Factory pattern
    print(f"Creating new LLM client for {model_name}")
    llm_client = None

    if "gemini" in model_name.lower():
        llm_client = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.4,
            max_retries=2,
            google_api_key=api_key,
        )

    else:
        raise ValueError(f"Unsupported model: {model_name}")

    _llm_agents[model_name] = llm_client
    return llm_client
