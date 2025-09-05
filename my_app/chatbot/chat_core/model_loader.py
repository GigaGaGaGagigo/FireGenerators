import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_upstage import UpstageEmbeddings
from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler

ENV_PATH: Path = Path(__file__).parents[3] / ".env"
# OPENAI_MODEL_NAME: str = "gpt-5-mini"
OPENAI_MODEL_NAME: str = "gpt-4.1-mini"

# Only load .env file if it exists and we're not in a test environment
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

_llm_models = {}
_llm_models_with_tool = {}


def get_llm_models(model_name: str, tool: bool = False):
    if tool:
        return _get_model_with_tool(model_name)

    if model_name in _llm_models:
        return _llm_models[model_name]

    print(f"Creating new LLM client for {model_name}")

    model: ChatOpenAI = ChatOpenAI(
        model=model_name,
        temperature=0.4,
        max_retries=0,
        api_key=os.getenv("OPENAI_API_KEY"),  # pyright: ignore[reportArgumentType]
        # reasoning_effort="low",
    )

    _llm_models[model_name] = model

    return _llm_models[model_name]


def _get_model_with_tool(model_name: str):
    from my_app.chatbot.chat_core.nodes import (
        AnalyzeProfile,
        GenerateFollowUp,
        RequestHumanInput,
    )

    if model_name in _llm_models_with_tool:
        return _llm_models_with_tool[model_name]

    print(f"Creating new LLM client for {model_name} with tool")

    model: ChatOpenAI = ChatOpenAI(
        model=model_name,
        temperature=0.4,
        max_retries=0,
        api_key=os.getenv("OPENAI_API_KEY"),  # pyright: ignore[reportArgumentType]
        # reasoning_effort="low",
    )
    model_with_tool = model.bind_tools(
        [RequestHumanInput, AnalyzeProfile, GenerateFollowUp]
    )
    _llm_models_with_tool[model_name] = model_with_tool
    return _llm_models_with_tool[model_name]


def get_embedding_model():
    model = UpstageEmbeddings(
        api_key=os.getenv("UPSTAGE_API_KEY"),  # type: ignore
        model="embedding-query",
    )

    return model


def get_langfuse_handler():
    Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST"),
    )

    # Initialize the Langfuse handler
    langfuse_handler = CallbackHandler()

    return langfuse_handler


def flush_langfuse():
    Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST"),
    )
    langfuse = get_client()
    langfuse.flush()
