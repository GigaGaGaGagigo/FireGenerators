import time
from pathlib import Path

from IPython.display import Image, display
from langchain_core.messages import AIMessage, AnyMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from my_app.chatbot.chat_core.nodes import (
    analyze_user_answers,
    batch_filter_node,
    call_llm,
    compact_user_answer,
    create_followup_qa,
    determine_next_node,
    generate_greeting_and_news,
    generate_greeting_message,
    generate_queries_node,
    generate_report_node,
    present_predefined_questions,
    process_human_input_tool,
    summarize_user_profile,
    update_user_meta_data,
    update_user_profile,
    web_search_node,
)
from my_app.chatbot.chat_core.state import (
    InputState,
    OutputState,
    OverallState,
)


class GraphBuilder:
    def __init__(self):
        self.memory: InMemorySaver | None = InMemorySaver()
        self.graph: CompiledStateGraph | None = None

    def _determine_initial_node(self, state: OverallState) -> str | None:
        profile_status: str | None = state.user_meta_data.get("profile_status", None)

        if profile_status is None:
            raise ValueError("Profile status is not found in the user meta data.")

        if profile_status == "completed":
            return "generate_queries"
        else:
            return "ask_to_new_user"

    def _finished_chat_with_user(self, state: OverallState):
        ai_message: str = (
            f"{state.user_meta_data['name']}님, 이제 다른 메뉴를 체험해볼까요?"
        )
        return {
            "logs": [
                {
                    "level": "info",
                    "message": "Finished chat with user",
                    "timestamp": time.time(),
                }
            ],
            "messages": [AIMessage(content=ai_message)],
            "search_dataset": state.search_dataset,
        }

    def _route_after_agent(self, state: OverallState):
        messages: list[AnyMessage] = state.messages
        last_message: AnyMessage = messages[-1]

        try:
            tool_calls = getattr(last_message, "tool_calls", None)

            if not tool_calls:
                return START

            if tool_calls[0]["name"] == "RequestHumanInput":
                return "request_input"
            elif tool_calls[0]["name"] == "GenerateFollowUp":
                return "add_qa"
            elif tool_calls[0]["name"] == "AnalyzeProfile":
                return "analyze_answers"
            return START

        except AttributeError:
            return START

    def _route_after_update(self, state: OverallState):
        profile_status = state.user_meta_data.get("profile_status", None)

        try:
            if profile_status == "completed":
                return "summarize_user_profile"
            elif profile_status == "onboarding" or profile_status == "editing":
                return "ask_to_new_user"

        except AttributeError:
            return START

    def build_workflow(self):
        workflow = StateGraph(
            OverallState, input_schema=InputState, output_schema=OutputState
        )

        workflow.add_node("start_chat", generate_greeting_message)
        workflow.add_node("ask_to_new_user", present_predefined_questions)
        workflow.add_node("agent", call_llm)
        workflow.add_node("add_qa", create_followup_qa)
        workflow.add_node("compact_user_answer", compact_user_answer)
        workflow.add_node("determine_next", determine_next_node)
        workflow.add_node("request_input", process_human_input_tool)
        workflow.add_node("analyze_answers", analyze_user_answers)
        workflow.add_node("update_user_profile", update_user_profile)
        workflow.add_node("summarize_user_profile", summarize_user_profile)
        workflow.add_node("update_user_meta_data", update_user_meta_data)
        workflow.add_node("finished_chat", self._finished_chat_with_user)
        workflow.add_node("generate_greeting_and_news", generate_greeting_and_news)
        workflow.add_node("generate_queries", generate_queries_node)
        workflow.add_node("web_search", web_search_node)
        workflow.add_node("filter_results", batch_filter_node)
        workflow.add_node("generate_report", generate_report_node)

        workflow.add_edge(START, "start_chat")
        workflow.add_conditional_edges(
            "start_chat",
            self._determine_initial_node,
            path_map=["ask_to_new_user", "generate_queries"],
        )
        workflow.add_edge("ask_to_new_user", "agent")

        workflow.add_conditional_edges(
            "agent",
            self._route_after_agent,
            path_map=["request_input", "add_qa", "analyze_answers"],
        )

        workflow.add_edge("request_input", "compact_user_answer")
        workflow.add_edge("compact_user_answer", "determine_next")
        workflow.add_edge("determine_next", "agent")
        workflow.add_edge("add_qa", "agent")
        workflow.add_edge("analyze_answers", "update_user_profile")

        workflow.add_conditional_edges(
            "update_user_profile",
            self._route_after_update,
            path_map=["summarize_user_profile", "ask_to_new_user"],
        )

        workflow.add_edge("summarize_user_profile", "update_user_meta_data")
        workflow.add_edge("update_user_meta_data", END)
        workflow.add_edge("generate_queries", "web_search")
        workflow.add_edge("web_search", "filter_results")
        workflow.add_edge("filter_results", "generate_report")
        workflow.add_edge("generate_report", "finished_chat")
        workflow.add_edge("finished_chat", END)

        self.memory = InMemorySaver()

        self.graph = workflow.compile(checkpointer=self.memory)
        return self.graph

    def visualize_graph(self, save_path: Path | str | None = None) -> None:
        if save_path is None:
            output_path: Path = Path(__file__).parents[1] / "utils"
            output_file = str(output_path / "graph_recursion_limit.png")
            save_path = output_file

        if self.graph is not None:
            display(
                Image(
                    self.graph.get_graph().draw_mermaid_png(
                        output_file_path=str(save_path)
                    )
                )
            )
        else:
            raise ValueError(
                "Graph has not been initialized. Please build the graph before visualizing."
            )
