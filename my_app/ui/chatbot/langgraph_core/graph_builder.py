"""
WRITER: Kang Joseph
DATE: 2025-08-01
DESCRIPTION:
This module provides a function to build a langgraph graph.
"""

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from my_app.ui.chatbot.langgraph_core.nodes import (
    analyze_user_goal,
    build_output_state_from_analysis,
    evaluation_analysis,
    generate_follow_up_questions,
    initialize_conversation,
    prepare_fixed_question_set,
    route_after_evaluation,
    route_after_initialize_conversation,
    route_after_update_profile_status,
    update_profile_status,
)
from my_app.ui.chatbot.langgraph_core.state.state import (
    InputState,
    OutputState,
    OverallState,
)


class GraphBuilder:
    def __init__(self, interrupt_before: list[str] | None = None):
        self.workflow = StateGraph(
            OverallState, input_schema=InputState, output_schema=OutputState
        )

        self.workflow.add_node("initialize_conversation", initialize_conversation)
        self.workflow.add_node("prepare_fixed_question_set", prepare_fixed_question_set)
        self.workflow.add_node(
            "generate_follow_up_questions", generate_follow_up_questions
        )
        self.workflow.add_node("analyze_user_goal", analyze_user_goal)
        self.workflow.add_node("evaluation_analysis", evaluation_analysis)
        self.workflow.add_node("update_profile_status", update_profile_status)
        self.workflow.add_node(
            "build_output_state_from_analysis", build_output_state_from_analysis
        )

        self.config = RunnableConfig(
            recursion_limit=4,
            configurable={"thread_id": "1"},
            tags=["my-rag"],  # Tag
        )

        self.memory = MemorySaver()

        self.workflow.add_edge(START, "initialize_conversation")
        self.workflow.add_conditional_edges(
            "initialize_conversation",
            route_after_initialize_conversation,
            {
                "onboarding": "prepare_fixed_question_set",
                "editing": "prepare_fixed_question_set",
                "completed": END,  # TODO: 기존 사용자 subgraph 추가 필요
            },
        )
        # TODO(human): Remove this conflicting direct edge that overrides conditional routing
        self.workflow.add_edge(
            "prepare_fixed_question_set", "generate_follow_up_questions"
        )
        self.workflow.add_edge("generate_follow_up_questions", "analyze_user_goal")
        self.workflow.add_edge("analyze_user_goal", "evaluation_analysis")
        self.workflow.add_conditional_edges(
            "evaluation_analysis",
            route_after_evaluation,
            {
                "valid": "update_profile_status",
                "invalid": "analyze_user_goal",
            },
        )
        self.workflow.add_edge("evaluation_analysis", "update_profile_status")
        self.workflow.add_conditional_edges(
            "update_profile_status",
            route_after_update_profile_status,
            {
                "onboarding": "prepare_fixed_question_set",
                "editing": "prepare_fixed_question_set",
                "completed": "build_output_state_from_analysis",
            },
        )
        self.workflow.add_edge("build_output_state_from_analysis", END)
        if interrupt_before is not None:
            self.graph = self.workflow.compile(
                checkpointer=self.memory, interrupt_before=interrupt_before
            )
        else:
            self.graph = self.workflow.compile(checkpointer=self.memory)

    def invoke(
        self,
        input: InputState,
        config: RunnableConfig | None = None,
        interrupt_before: list[str] | None = None,
    ):
        if config is None:
            config = self.config

        return self.graph.invoke(
            input, config=config, interrupt_before=interrupt_before
        )

    def get_state(self, config: RunnableConfig | None = None) -> OverallState:
        """Return the current OverallState values from the compiled graph.

        This unwraps the internal state snapshot to expose the typed OverallState,
        so the UI layer can render directly from a single source of truth.
        """
        if config is None:
            config = self.config
        # langgraph state snapshot exposes `.values` for typed state
        state_snapshot = self.graph.get_state(config)
        # Ensure the returned value is of type OverallState
        if isinstance(state_snapshot.values, OverallState):
            return state_snapshot.values
        else:
            return OverallState(**state_snapshot.values)
