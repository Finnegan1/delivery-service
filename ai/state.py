import typing

import ai.ai_constants

class State(
    typing.TypedDict
):
    question: str
    goal_type: ai.ai_constants.GOAL_TYPES_LITERAL