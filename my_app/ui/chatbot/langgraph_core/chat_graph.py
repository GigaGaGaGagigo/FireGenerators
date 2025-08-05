"""
WRITER: Kang Joseph
DATE: 2025-08-02
DESCRIPTION:
This file defines the chat graph for the chatbot.

TODO:
"""

from langgraph.graph import END, START, StateGraph

from my_app.ui.chatbot.langgraph_core.nodes import (
    generate_onboarding_response,
)
from my_app.ui.chatbot.langgraph_core.state import ChatState
from my_app.ui.chatbot.utils.draw_graphs import visualize_graph


def create_chat_graph():
    workflow = StateGraph(ChatState)

    workflow.add_node("onboarding", generate_onboarding_response)
    workflow.add_edge(START, "onboarding")
    workflow.add_edge("onboarding", END)

    return workflow.compile()


class ChatGraphManager:
    """
    Chat Graph를 관리하는 헬퍼 클래스
    """

    def __init__(self):
        self.graph = create_chat_graph()

    def visualize_graph(self):
        visualize_graph(self.graph)

    def process_message(self, current_state: ChatState):
        result = self.graph.invoke(current_state)

        return result

    def stream_message(self, current_state: ChatState):
        """
        메시지를 스트리밍 방식으로 처리
        """
        for event in self.graph.stream(current_state):
            yield event

    async def aprocess_message(self, current_state: ChatState):
        # 비동기 그래프 실행
        result = await self.graph.ainvoke(current_state)

        return result
