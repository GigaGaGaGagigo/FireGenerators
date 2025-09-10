"""
WRITER: Kang Joseph
DATE: 2025-08-12
DESCRIPTION: This file defines the state structure used throughout the chat workflow.
TODO:
- Add merge_user_answers function to merge user answers from different nodes
- Add more detailed description to each field
- Optimize the state structure to reduce the number of fields
"""

from operator import add

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field
from typing_extensions import Annotated, Any, Dict, List, Tuple


def merge_processed_answers(
    left: Dict[str, List[Tuple[str, str]]] | None,
    right: Dict[str, List[Tuple[str, str]]] | None,
) -> Dict[str, List[Tuple[str, str]]]:
    left = left if isinstance(left, dict) else {}
    right = right if isinstance(right, dict) else {}

    merged: Dict[str, List[Tuple[str, str]]] = {}
    for k, v in left.items():
        merged[k] = list(v)

    for category, answers in right.items():
        if category in merged:
            merged[category] = list(merged[category]) + list(answers)
        else:
            merged[category] = list(answers)

    return merged


def merge_compacted_answers(
    left: Dict[str, List[str]] | None,
    right: Dict[str, List[str]] | None,
) -> Dict[str, List[str]]:
    left = left if isinstance(left, dict) else {}
    right = right if isinstance(right, dict) else {}

    merged: Dict[str, List[str]] = {}
    for k, v in left.items():
        merged[k] = list(v)

    for category, answers in right.items():
        if category in merged:
            merged[category] = list(merged[category]) + list(answers)
        else:
            merged[category] = list(answers)

    return merged


class InputState(BaseModel):
    target_profile_category: Annotated[
        None | List[str],
        Field(description="User profile category to set"),
    ]
    user_meta_data: Annotated[
        Dict[str, Any],
        Field(
            default_factory=dict,
            description="Metadata for the user, loaded from the database. Contains fields such as name, profile_status, investment_goal, investment_emotions, interests_categories, investment_level, knowledge_level, risk_tolerance",
        ),
    ]


class OverallState(BaseModel):
    logs: Annotated[List[Dict[str, Any]], add] = Field(
        default_factory=list,
        description="A list for storing system-level logs for debugging and tracking.",
    )
    messages: Annotated[
        List[AnyMessage],
        add,
        Field(default_factory=list, description="All messages in the conversation."),
    ]
    questions_by_category: Annotated[
        Dict[str, Dict[str, list]],
        Field(
            default_factory=dict,
            description="A dictionary of questions, grouped by category. Each question dictionary contains question_id as key and questions and options.",
        ),
    ]
    target_profile_category: Annotated[
        List[str],
        Field(description="User profile category to set", default=None),
    ]
    user_answers_by_category: Annotated[
        Dict[str, List[Tuple[str, str]]],
        merge_processed_answers,
        Field(
            default_factory=dict,
            description="User's answers to questions, grouped by category. Each category contains a list of tuples, each containing the question_id and a tuple of questions and user's answer.",
        ),
    ]
    user_answers_compacted: Annotated[
        Dict[str, list[str]],
        merge_compacted_answers,
        Field(
            default_factory=dict,
            description="User's answers to questions, grouped by category. Each category contains a list of strings, each containing the user's compacted answer.",
        ),
    ]
    user_meta_data: Annotated[
        Dict[str, Any],
        Field(
            default_factory=dict,
            description="User Meta data that is updated throughout the conversation. Contains name, profile status, investment goal, investment emotions, interests categories, investment level, knowledge level, risk tolerance, user profile summary",
        ),
    ]
    user_meta_data_updated: Annotated[
        Dict[str, Any],
        Field(
            default_factory=dict,
            description="User Meta data that is updated throughout the conversation. Contains name, profile status, investment goal, investment emotions, interests categories, investment level, knowledge level, risk tolerance, user profile summary",
        ),
    ]
    search_dataset: Annotated[
        Dict[str, Any],
        Field(
            default_factory=dict,
            description="Search dataset that is updated throughout the conversation. Includes search queries, search results, and report.",
        ),
    ]


class OutputState(BaseModel):
    logs: Annotated[List[Dict[str, Any]], add] = Field(
        default_factory=list,
        description="A list for storing system-level logs for debugging and tracking.",
    )
    messages: Annotated[
        List[AnyMessage],
        add_messages,
        Field(default_factory=list, description="All messages in the conversation"),
    ]
    user_meta_data: Annotated[
        Dict[str, Any],
        Field(
            default_factory=dict,
            description="The final User Meta data that is consolidated throughout the conversation",
        ),
    ]
    user_meta_data_updated: Annotated[
        Dict[str, Any],
        Field(
            default_factory=dict,
            description="User Meta data that is updated throughout the conversation. Contains name, profile status, investment goal, investment emotions, interests categories, investment level, knowledge level, risk tolerance, user profile summary",
        ),
    ]
    search_dataset: Annotated[
        Dict[str, Any],
        Field(
            default_factory=dict,
            description="Search dataset that is updated throughout the conversation. Includes search queries, search results, and report.",
        ),
    ]
