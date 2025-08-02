"""
WRITER: Kang Joseph
DATE: 2025-08-01
DESCRIPTION:
This file defines the state structure used throughout the chat workflow.

TODO: Add variables after adding functions.
"""

from typing import Annotated, TypedDict

from langgraph.graph import add_messages


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]
