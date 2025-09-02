import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

ENV_PATH: Path = Path(__file__).parents[3] / ".env"
GEMINI_MODEL_NAME: str = "gemini-2.5-flash"
OPENAI_MODEL_NAME: str = "gpt-5-mini"

# Only load .env file if it exists and we're not in a test environment
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

_llm_models = {}
_llm_models_with_tool = {}
api_key: str | None = os.getenv("GOOGLE_API_KEY")


def get_llm_models(model_name: str, tool: bool = False):
    from my_app.chatbot.chat_core.nodes import (
        AnalyzeProfile,
        GenerateFollowUp,
        RequestHumanInput,
    )

    if model_name in _llm_models:
        return _llm_models[model_name]

    # Factory pattern
    print(f"Creating new LLM client for {model_name}")

    model: ChatOpenAI = ChatOpenAI(
        model=model_name,
        temperature=0.4,
        max_retries=0,
        api_key=os.getenv("OPENAI_API_KEY"),
        reasoning_effort="low",
    )

    if tool:
        model_with_tool = model.bind_tools(
            [RequestHumanInput, AnalyzeProfile, GenerateFollowUp]
        )
        _llm_models[model_name + "_with_tool"] = model_with_tool
        return _llm_models[model_name + "_with_tool"]

    return _llm_models[model_name]


def get_llm_models_with_tool(model_name: str):
    from my_app.chatbot.chat_core.nodes import (
        AnalyzeProfile,
        GenerateFollowUp,
        RequestHumanInput,
    )

    if model_name in _llm_models:
        return _llm_models[model_name + "_with_tool"]

    # 순환 import 방지를 위해 함수 내부에서 import

    llm_client = ChatOpenAI(
        model="gpt-5",
        temperature=0.4,
        max_retries=0,
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    llm_client = llm_client.bind_tools(
        [RequestHumanInput, AnalyzeProfile, GenerateFollowUp]
    )

    _llm_models_with_tool[model_name + "_with_tool"] = llm_client

    return llm_client


def get_gpt_agent_with_tool(model_name: str):
    from my_app.chatbot.chat_core.nodes import (
        AnalyzeProfile,
        GenerateFollowUp,
        RequestHumanInput,
    )

    if model_name in _llm_models_with_tool:
        return _llm_models_with_tool[model_name + "_with_tool"]

    llm_client = ChatOpenAI(
        model="gpt-5-nano",
        temperature=0.4,
        max_retries=0,
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    llm_client = llm_client.bind_tools(
        [RequestHumanInput, AnalyzeProfile, GenerateFollowUp]
    )

    _llm_models_with_tool[model_name + "_with_tool"] = llm_client

    return llm_client
