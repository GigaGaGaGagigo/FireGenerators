import time

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from my_app.chatbot.chat_core.model_loader import get_embedding_model
from my_app.chatbot.chat_core.state import OutputState, OverallState
from my_app.chatbot.services import ProfileService


def update_user_profile(state: OverallState, config: RunnableConfig):
    profile_service: ProfileService | None = None
    configurable = config.get("configurable")

    if configurable and hasattr(configurable, "get"):
        profile_service = configurable.get("profile_service")

    if profile_service is not None:
        current_category = state.target_profile_category[0]
        current_data = state.user_meta_data[current_category]

        if current_category == "risk_tolerance":
            current_data = int(current_data)
        elif (
            current_category == "investment_level"
            or current_category == "knowledge_level"
        ):
            current_data = current_data

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
                "edit_mode": "FINISHED",
            },
        }
    else:
        return {
            "target_profile_category": state.target_profile_category,
            "user_meta_data": {
                **state.user_meta_data,
                "profile_status": "completed",
                "edit_mode": "UNCOMPLETED",
            },
        }


def update_user_meta_data(state: OverallState, config: RunnableConfig):
    model = get_embedding_model()

    user_profile_summary = state.user_meta_data["user_profile_summary"]

    user_profile_vector = model.embed_query(user_profile_summary)

    profile_service: ProfileService | None = None
    if "configurable" in config and config["configurable"] is not None:
        profile_service = config["configurable"].get("profile_service")

    if profile_service is not None:
        current_category = "user_summary"
        current_data = user_profile_summary

        profile_service.update_category(current_category, current_data)
        profile_service.update_category("user_meta_vector", user_profile_vector)

    ai_message = f"{state.user_meta_data['name']}의 분석이 완료되었습니다. 이제 다른 메뉴를 체험해볼까요?"

    return OutputState(
        logs=[
            {
                "level": "info",
                "message": "User profile summary updated",
                "timestamp": time.time(),
            }
        ],
        messages=[AIMessage(content=ai_message)],
        user_meta_data={
            **state.user_meta_data,
            "user_profile_summary": user_profile_summary,
        },
        user_meta_data_updated={},
        search_dataset={},
    )


def update_user_profile_based_on_report(state: OverallState, config: RunnableConfig):
    profile_service: ProfileService | None = None
    configurable = config.get("configurable")

    if configurable and hasattr(configurable, "get"):
        profile_service = configurable.get("profile_service")

    if profile_service is not None:
        combine_categories = [
            "interests_categories",
            "investment_emotions",
            "investment_goal",
            "risk_tolerance",
        ]

        for current_category in combine_categories:
            current_data = state.user_meta_data[current_category]

            profile_service.update_category(current_category, current_data)

        # log update code
        profile_service.update_news_logs(state.search_dataset["report"])

        edit_mode = "FINISHED"

        ai_message = f"{state.user_meta_data['name']}님 과의 대화를 통해 새로운 정보가 업데이트 되었습니다."

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
                "edit_mode": edit_mode,
            },
            "messages": [AIMessage(content=ai_message)],
        }
    else:
        return {
            "target_profile_category": state.target_profile_category,
            "user_meta_data": {
                **state.user_meta_data,
                "profile_status": "completed",
                "edit_mode": "UNCOMPLETED",
            },
        }
