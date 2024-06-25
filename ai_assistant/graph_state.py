import typing
import typing_extensions

import langgraph.graph.message
import langchain_core.messages

class State(
    typing_extensions.TypedDict
):
    #messages: typing.Annotated[list[langchain_core.messages.MessageLikeRepresentation], langgraph.graph.message.add_messages]
    agent_messages: list[langchain_core.messages.MessageLikeRepresentation]
    agent_task: str
    # TODO generate Type
    next_agent: typing.Literal['planning_agent', 'supervisor_agent', 'security_agent', 'ocm_agent']
    current_plan: str
    executed_tasks_results: dict[str, str]
    question: str
    answer: str|None
