import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

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

        # chat_graph_manager.visualize_graph()

        question = "안녕하세요 처음 챗봇을 사용해요. 저는 요셉이라고 해요."
        print(f"📝 Question: {question}")

        # 방법 1: 동기 처리 (일반적인 방법)
        print("\n--- Synchronous processing ---")
        result = chat_graph_manager.process_message(
            {"messages": [HumanMessage(content=question)]}
        )

        print("✅ 처리 완료!")
        print("📄 결과:", result)

        # 응답 메시지 추출
        if "messages" in result and result["messages"]:
            for msg in result["messages"]:
                if hasattr(msg, "content"):
                    print("🤖 AI 응답:", msg.content)
                else:
                    print("🤖 AI 응답:", msg)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
