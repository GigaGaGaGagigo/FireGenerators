import time

from langchain_core.runnables import RunnableConfig

from my_app.chatbot.langgraph_core.state import OverallState
from my_app.chatbot.services import ProfileService


def update_user_profile(state: OverallState, config: RunnableConfig):
    profile_service: ProfileService | None = config["configurable"].get(
        "profile_service"
    )

    if profile_service is not None:
        # target_profile_category가 None이거나 비어있는 경우 안전하게 처리
        if not state.target_profile_category or len(state.target_profile_category) == 0:
            return {
                "target_profile_category": [],
                "user_meta_data": {
                    **state.user_meta_data,
                    "profile_status": "completed",
                },
            }
        
        current_category = state.target_profile_category[0]
        current_data = state.user_meta_data.get(current_category, {})

        profile_service.update_category(current_category, current_data)

        state.target_profile_category.pop(0)

        if len(state.target_profile_category) == 0:
            current_status = "completed"
        elif len(state.target_profile_category) < 6:
            current_status = "editing"
        else:
            current_status = "onboarding"

        return {
            "logs": [
                {
                    "level": "info",
                    "message": "User profile updated",
                    "timestamp": time.time(),
                }
            ],
            "target_profile_category": state.target_profile_category,
            "user_meta_data": {
                **state.user_meta_data,
                "profile_status": current_status,
            },
        }
    else:
        return {
            "target_profile_category": state.target_profile_category or [],
            "user_meta_data": {
                **state.user_meta_data,
                "profile_status": "completed",
            },
        }
