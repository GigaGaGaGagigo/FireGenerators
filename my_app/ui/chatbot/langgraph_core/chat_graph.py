"""
WRITER: Kang Joseph
DATE: 2025-08-02
DESCRIPTION:
This file defines the chat graph for the chatbot.

TODO:

START - Conversation Node - Analysis_Node - Response_node - END
"""

from langgraph.graph import END, START, StateGraph

from my_app.ui.chatbot.langgraph_core.nodes import check_analysis_requirements
from my_app.ui.chatbot.langgraph_core.state import ChatState


def create_chatgraph():
    workflow = StateGraph(ChatState)

    workflow.add_node("is_analysis_required", check_analysis_requirements)
    workflow.add_edge(START, "is_analysis_required")
    workflow.add_edge("is_analysis_required", END)

    return workflow.compile()


class ChatGraphManager:
    """
    Chat Graph를 관리하는 헬퍼 클래스
    """

    def __init__(self):
        self.graph = create_chatgraph()

    def process_message(self, chatstate: ChatState):
        result = self.graph.invoke(chatstate)

        return result

    async def aprocess_message(self, current_state: ChatState):
        # 비동기 그래프 실행
        result = await self.graph.ainvoke(current_state)

        return result
