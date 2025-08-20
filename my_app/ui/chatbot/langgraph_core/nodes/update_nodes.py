from ui.chatbot.langgraph_core.state import OverallState


def update_profile_status(
    state: OverallState,
):
    target_category = state.target_profile_category[0]

    if target_category == "investment_goal":
        analyzed_user_data = state.investment_goal
    elif target_category == "investment_emotions":
        analyzed_user_data = state.investment_emotions
    elif target_category == "interests_categories":
        analyzed_user_data = state.interests_categories
    elif target_category == "investment_level":
        analyzed_user_data = state.investment_level
    elif target_category == "knowledge_level":
        analyzed_user_data = state.knowledge_level
    else:
        raise ValueError(f"Invalid target_profile_category: {target_category}")

    if (
        len(analyzed_user_data) > 0
        and state.evaluation_results[target_category] == "valid"
    ):
        state.target_profile_category.pop(0)

    if len(state.target_profile_category) == 0:
        profile_status = "completed"
    elif len(state.target_profile_category) > 0 and len(state.evaluation_results) < 5:
        profile_status = "editing"
    else:
        profile_status = "onboarding"

    return {
        "target_profile_category": state.target_profile_category,
        "profile_status": profile_status,
    }
