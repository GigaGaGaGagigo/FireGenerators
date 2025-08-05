import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parents[3]
sys.path.insert(0, str(project_root))

# Set testing environment
os.environ["TESTING"] = "true"

try:
    from my_app.ui.chatbot.langgraph_core.llm_agents import (
        ENV_PATH,
        GEMINI_MODEL_NAME,
        get_llm_agents,
    )
    from my_app.ui.chatbot.langgraph_core.nodes import conversation_node
    from my_app.ui.chatbot.langgraph_core.state import ChatState
except ImportError:
    print("ImportError: Failed to import ChatGraphManager")
    sys.exit(1)


def test_conversation_node():
    result = conversation_node.check_analysis_requirements(
        ChatState(user_messages=["안녕하세요"], ai_messages=[], is_analysis_required="")
    )
    print(result)


def test_llm_agents():
    llm = get_llm_agents(GEMINI_MODEL_NAME)
    print(llm)

    return llm


if __name__ == "__main__":
    # test_conversation_node()
    llm = test_llm_agents()
    llm.invoke("안녕하세요")
    print(ENV_PATH)
