import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from my_app.ui.chatbot.langgraph_core.chat_graph import ChatGraphManager
except Exception as e:
    print(f"❌ Error: {e}")

    import traceback

    traceback.print_exc()
    sys.exit(1)


if __name__ == "__main__":
    print("🤖 Starting chatbot test...")

    try:
        chat_graph_manager = ChatGraphManager()
        print("✅ ChatGraphManager created successfully")

        chat_graph_manager.visualize_graph()

        question = "서울의 유명한 맛집 10군데를 추천해주세요"
        print(f"📝 Question: {question}")

        # 방법 1: 동기 처리 (일반적인 방법)
        print("\n--- Synchronous processing ---")
        result = chat_graph_manager.process_message({"messages": [("user", question)]})
        print(f"Result: {result}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
