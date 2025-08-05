import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parents[3]
sys.path.insert(0, str(project_root))

# Set testing environment
os.environ["TESTING"] = "true"

try:
    from my_app.ui.chatbot.langgraph_core.chat_graph import ChatGraphManager
    from my_app.ui.chatbot.langgraph_core.state import ChatState

except ImportError:
    print("ImportError: Failed to import ChatGraphManager")
    sys.exit(1)

if __name__ == "__main__":
    print("🤖 Starting chatbot test...")

    chat_graph_manager = ChatGraphManager()

    user_input = "안녕? 반가워"

    print(project_root)

    result = chat_graph_manager.process_message(
        ChatState(user_messages=[user_input], ai_messages=[], is_analysis_required="")
    )

    print(result)
