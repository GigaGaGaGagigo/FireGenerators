import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

ENV_PATH: Path = Path(__file__).parents[3] / ".env"
GEMINI_MODEL_NAME: str = "gemini-2.5-flash"
OPENAI_MODEL_NAME: str = "gpt-5-nano"

# Only load .env file if it exists and we're not in a test environment
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

_llm_agents = {}
_llm_agents_with_tool = {}
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
            max_retries=0,
            google_api_key=api_key,
        )

    else:
        raise ValueError(f"Unsupported model: {model_name}")

    _llm_agents[model_name] = llm_client
    return llm_client


def get_llm_agent_with_tool(model_name: str):
    if model_name in _llm_agents:
        return _llm_agents[model_name]

    # 순환 import 방지를 위해 함수 내부에서 import
    from my_app.chatbot.langgraph_core.nodes import (
        AnalyzeProfile,
        GenerateFollowUp,
        RequestHumanInput,
    )

    llm_client = ChatOpenAI(
        model="gpt-5",
        temperature=0.4,
        max_retries=0,
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    llm_client = llm_client.bind_tools(
        [RequestHumanInput, AnalyzeProfile, GenerateFollowUp]
    )

    _llm_agents_with_tool[model_name] = llm_client

    return llm_client


def get_gpt_agent_with_tool(model_name: str):
    if model_name in _llm_agents_with_tool:
        return _llm_agents_with_tool[model_name]

    from my_app.chatbot.langgraph_core.nodes import (
        AnalyzeProfile,
        GenerateFollowUp,
        RequestHumanInput,
    )

    llm_client = ChatOpenAI(
        model="gpt-5-nano",
        temperature=0.4,
        max_retries=0,
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    llm_client = llm_client.bind_tools(
        [RequestHumanInput, AnalyzeProfile, GenerateFollowUp]
    )

    _llm_agents_with_tool[model_name] = llm_client

    return llm_client
