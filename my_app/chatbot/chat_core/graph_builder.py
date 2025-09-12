import time
from pathlib import Path

from IPython.display import Image, display
from langchain_core.messages import AIMessage, AnyMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from my_app.chatbot.chat_core.nodes import (
    analyze_user_answers,
    analyze_user_answers_based_on_report,
    ask_to_start_conversation,
    batch_filter_node,
    call_llm,
    combine_user_meta_data,
    compact_user_answer,
    compact_user_answer_based_on_report,
    create_followup_qa,
    decide_to_continue_conversation,
    decide_to_present_questions,
    determine_next_node,
    determine_next_user_node,
    generate_greeting_message,
    generate_queries_node,
    generate_questions_based_on_report,
    generate_report_node,
    present_predefined_questions,
    present_questions_based_on_report,
    process_human_input_tool,
    process_to_start_conversation,
    summarize_user_profile,
    talk_llm,
    update_user_meta_data,
    update_user_profile,
    update_user_profile_based_on_report,
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
                return "finished_chat"

            if tool_calls[0]["name"] == "RequestHumanInput":
                return "request_input"
            elif tool_calls[0]["name"] == "GenerateFollowUp":
                return "add_qa"
            elif tool_calls[0]["name"] == "AnalyzeProfile":
                return "analyze_answers"
            return "finished_chat"

        except AttributeError:
            return "finished_chat"

    def _route_after_user_agent(self, state: OverallState):
        messages: list[AnyMessage] = state.messages
        last_message: AnyMessage = messages[-1]

        tool_calls = getattr(last_message, "tool_calls", None)

        if not tool_calls:
            return "combine_data"

        tool_name = tool_calls[0]["name"]

        route_map = {
            "RequestUserInput": "request_to_user",
            "PresentQuestions": "present_to_user",
            "GenerateQuestions": "gen_based_on_report",
            "CombineUserMetaData": "combine_data",
        }

        return route_map.get(tool_name, "combine_data")

    def _route_after_update(self, state: OverallState):
        profile_status = state.user_meta_data.get("profile_status", None)

        try:
            if profile_status == "completed":
                return "summarize_user_profile"
            elif profile_status == "onboarding" or profile_status == "editing":
                return "ask_to_new_user"

        except AttributeError:
            return END

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
        workflow.add_node("generate_queries", generate_queries_node)
        workflow.add_node("web_search", web_search_node)
        workflow.add_node("filter_results", batch_filter_node)
        workflow.add_node("generate_report", generate_report_node)
        workflow.add_node("ask_to_user", ask_to_start_conversation)
        workflow.add_node("request_to_user", process_to_start_conversation)
        workflow.add_node("user_agent", talk_llm)
        workflow.add_node("gen_based_on_report", generate_questions_based_on_report)
        workflow.add_node("present_to_user", present_questions_based_on_report)
        workflow.add_node("compact_updated_data", compact_user_answer_based_on_report)
        workflow.add_node("analyze_updated_data", analyze_user_answers_based_on_report)
        workflow.add_node("combine_data", combine_user_meta_data)
        workflow.add_node("determine_next_user_node", determine_next_user_node)
        workflow.add_node("decide_to_continue", decide_to_continue_conversation)
        workflow.add_node("decide_to_present", decide_to_present_questions)
        workflow.add_node("update_profile", update_user_profile_based_on_report)

        workflow.add_edge(START, "start_chat")
        workflow.add_conditional_edges(
            "start_chat",
            self._determine_initial_node,
            path_map=[
                "ask_to_new_user",
                "generate_queries",
            ],
        )
        workflow.add_edge("ask_to_new_user", "agent")

        workflow.add_conditional_edges(
            "agent",
            self._route_after_agent,
            path_map=["request_input", "add_qa", "analyze_answers", "finished_chat"],
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

        # ==============↑ new user's workflow ==============
        # ==============↓ old user's workflow ==============

        workflow.add_edge("generate_queries", "web_search")
        workflow.add_edge("web_search", "filter_results")
        workflow.add_edge("filter_results", "generate_report")
        workflow.add_edge("generate_report", "ask_to_user")
        workflow.add_edge("ask_to_user", "user_agent")

        workflow.add_conditional_edges(
            "user_agent",
            self._route_after_user_agent,
            path_map=[
                "request_to_user",
                "present_to_user",
                "combine_data",
                "gen_based_on_report",
            ],
        )

        workflow.add_edge("gen_based_on_report", "decide_to_present")
        workflow.add_edge("decide_to_present", "user_agent")

        workflow.add_edge("request_to_user", "decide_to_continue")
        workflow.add_edge("decide_to_continue", "user_agent")

        workflow.add_edge("present_to_user", "compact_updated_data")
        workflow.add_edge("compact_updated_data", "analyze_updated_data")
        workflow.add_edge("analyze_updated_data", "determine_next_user_node")
        workflow.add_edge("determine_next_user_node", "user_agent")

        workflow.add_edge("combine_data", "update_profile")
        workflow.add_edge("update_profile", "finished_chat")
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
