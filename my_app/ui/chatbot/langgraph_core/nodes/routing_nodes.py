from typing_extensions import Literal, Optional

from ui.chatbot.langgraph_core.state import OverallState


def route_after_initialize_conversation(
    state: OverallState,
) -> Literal["onboarding", "editing", "completed"] | None:
    return state.profile_status


def route_after_evaluation(state: OverallState) -> Literal["valid", "invalid"]:
    return state.evaluation_results[state.target_profile_category[0]]


def route_after_update_profile_status(
    state: OverallState,
) -> Optional[Literal["onboarding", "editing", "completed"]]:
    return state.profile_status
