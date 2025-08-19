"""
WRITER: Kang Joseph
DATE: 2025-08-12
DESCRIPTION: This file defines the state structure used throughout the chat workflow.
"""

from langchain_core.messages import AIMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field
from typing_extensions import Annotated, Dict, List, Literal, Optional, Tuple

CATEGORY_KEYS: list[str] = [
    "investment_goal",
    "investment_emotions",
    "interests_categories",
    "investment_level",  # None'::text, 'beginner'::text, 'intermediate'::text, 'advanced'::text
    "knowledge_level",  # 'None'::text, 'beginner'::text, 'intermediate'::text, 'advanced'::text
]


def merge_user_answers(
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


class InputState(BaseModel):
    user_name: Annotated[str, Field(description="User name")]
    profile_status: Annotated[
        Literal["onboarding", "editing", "completed"],
        Field(description="User profile status (onboarding, editing, completed)"),
    ]
    target_profile_category: Annotated[
        None
        | List[
            Literal[
                "investment_goal",
                "investment_emotions",
                "interests_categories",
                "investment_level",
                "knowledge_level",
            ]
        ],
        Field(description="User profile category to set"),
    ]


class OverallState(BaseModel):
    user_name: Annotated[
        Optional[str],
        Field(default=None, description="user name"),
    ]

    ai_messages: Annotated[List[AIMessage], add_messages] = Field(
        default_factory=list, description="AI messages"
    )

    quiz_content_by_category: Annotated[
        Dict[
            Literal[
                "investment_goal",
                "investment_emotions",
                "interests_categories",
                "investment_level",
                "knowledge_level",
            ],
            Dict[str, list],
        ],
        Field(default_factory=dict, description="quiz content grouped by category"),
    ]

    profile_status: Annotated[
        Optional[Literal["onboarding", "editing", "completed"]],
        Field(
            default=None,
            description="User profile status (onboarding, editing, completed)",
        ),
    ]

    target_profile_category: Annotated[
        List[
            Literal[
                "investment_goal",
                "investment_emotions",
                "interests_categories",
                "investment_level",
                "knowledge_level",
            ]
        ],
        Field(description="User profile category to set", default=None),
    ]

    workflow_stage: Annotated[
        Optional[
            Literal[
                "serve_fixed_qa",
                "generate_qa",
                "finished_qa",
                "generated_analyzed_data",
            ]
        ],
        Field(description="AI state", default=None),
    ]

    answers_by_category: Annotated[
        Dict[
            Literal[
                "investment_goal",
                "investment_emotions",
                "interests_categories",
                "investment_level",
                "knowledge_level",
            ],
            List[Tuple[str, str]],
        ],
        merge_user_answers,
    ] = Field(default_factory=dict)

    evaluation_results: Annotated[
        Dict[
            Literal[
                "investment_goal",
                "investment_emotions",
                "interests_categories",
                "investment_level",
                "knowledge_level",
            ],
            Literal["valid", "invalid"],
        ],
        Field(default_factory=dict, description="Evaluation results"),
    ]

    evaluation_results_logs: Annotated[
        Dict[
            Literal[
                "investment_goal",
                "investment_emotions",
                "interests_categories",
                "investment_level",
                "knowledge_level",
            ],
            str,
        ],
        Field(default_factory=dict, description="Evaluation results logs"),
    ]

    investment_goal: Annotated[
        list[str],
        Field(default_factory=list, description="investment goal"),
    ]

    investment_emotions: Annotated[
        list[str],
        Field(default_factory=list, description="Investment emotions"),
    ]

    interests_categories: Annotated[
        list[str],
        Field(default_factory=list, description="Interests categories"),
    ]

    investment_level: Annotated[str, Field(default="", description="Investment level")]
    knowledge_level: Annotated[str, Field(default="", description="Knowledge level")]


class OutputState(BaseModel):
    ai_messages: Annotated[List[AIMessage], add_messages] = Field(
        default_factory=list,
        description="AI messages",
    )
    conclusion: Annotated[str, Field(default="", description="Conclusion")]
    investment_goal: Annotated[
        list[str],
        Field(default_factory=list, description="investment goal"),
    ]
    investment_emotions: Annotated[
        list[str],
        Field(default_factory=list, description="Investment emotions"),
    ]
    interests_categories: Annotated[
        list[str],
        Field(default_factory=list, description="Interests categories"),
    ]
    investment_level: Annotated[str, Field(default="", description="Investment level")]
    knowledge_level: Annotated[str, Field(default="", description="Knowledge level")]
