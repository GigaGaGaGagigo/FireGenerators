#!/usr/bin/env python3
"""
독립적인 LangGraph 챗봇 테스트 스크립트 (Streamlit 의존성 없음)
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 환경 변수 설정 (Streamlit 없이)
from dotenv import load_dotenv

env_path = project_root / ".env"
load_dotenv(env_path)

print(f"Project root: {project_root}")
print(f"API Key loaded: {'✅' if os.getenv('GOOGLE_API_KEY') else '❌'}")

try:
    from my_app.ui.chatbot.langgraph_core.chat_graph import ChatGraphManager
    print("✅ ChatGraphManager imported successfully")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)


def test_simple_conversation():
    """간단한 대화 테스트"""
    print("\n🤖 Testing simple conversation...")
    
    try:
        # ChatGraphManager 인스턴스 생성
        chat_manager = ChatGraphManager()
        print("✅ ChatGraphManager created successfully")
        
        # 테스트 메시지
        test_message = "안녕하세요! 투자에 대해 궁금한 점이 있어요."
        print(f"📝 Test message: {test_message}")
        
        # 메시지 처리
        result = chat_manager.process_message({
            "messages": [("user", test_message)]
        })
        
        print(f"📤 Result type: {type(result)}")
        print(f"📤 Result: {result}")
        
        # 응답 추출
        if "messages" in result and result["messages"]:
            last_message = result["messages"][-1]
            print(f"🤖 Bot response: {last_message}")
        else:
            print("❌ No response found in result")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


def test_multiple_turns():
    """멀티턴 대화 테스트"""
    print("\n💬 Testing multi-turn conversation...")
    
    try:
        chat_manager = ChatGraphManager()
        
        # 대화 시나리오
        conversation = [
            "안녕하세요!",
            "주식 투자를 시작하고 싶은데 어떻게 해야 할까요?",
            "초보자에게 추천하는 투자 방법이 있나요?"
        ]
        
        messages = []
        
        for i, user_input in enumerate(conversation, 1):
            print(f"\n--- Turn {i} ---")
            print(f"👤 User: {user_input}")
            
            # 기존 메시지에 새 메시지 추가
            messages.append(("user", user_input))
            
            # ChatGraph 실행
            result = chat_manager.process_message({"messages": messages})
            
            if "messages" in result and result["messages"]:
                # 새로운 AI 응답만 추출
                new_messages = result["messages"][len(messages):]
                for msg in new_messages:
                    print(f"🤖 Bot: {msg}")
                    messages.append(msg)
            
    except Exception as e:
        print(f"❌ Multi-turn test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("🚀 Starting standalone chatbot test...")
    print("=" * 50)
    
    # 기본 연결 테스트
    test_simple_conversation()
    
    # 멀티턴 대화 테스트
    test_multiple_turns()
    
    print("\n" + "=" * 50)
    print("✅ Test completed!")