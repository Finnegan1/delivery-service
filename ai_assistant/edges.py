from typing import Dict
import typing
import langchain
import langchain_core.output_parsers.openai_functions
import langgraph.graph
import ai_assistant.graph_state
import langchain_core.messages.function
import langchain_core.messages.ai
import json


def create_edge_conditional_routing(members: list[str]):
    # TODO generate Type
    # MemberType
    def conditional_routing(state: ai_assistant.graph_state.State)-> typing.Literal['ocm_agent', 'security_agent', 'planning_agent', 'summary_agent']:
        print(f'\n -> {state['next_agent']}\n')
        return state['next_agent']

    return conditional_routing

def tool_router(state: ai_assistant.graph_state.State) -> typing.Literal["tools", "agent_cleanup"]:
    """Use in the conditional_edge to route to the ToolNode if the last Message has tool calls, otherwise, routes back to the supervisor_agend."""
    if agent_messages := state.get("agent_messages", []):
        ai_message = agent_messages[-1]
    else:
        raise ValueError(f"No messages found in input state to tool edge: {state}")

    if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        print(f"\n -> tools\n")
        return "tools"

    print("\n -> agent_cleanup\n")
    return "agent_cleanup"

def tool_back_to_agent(state: ai_assistant.graph_state.State):
    '''Routes back to the agend, the graph visited last.'''
    print(f"\n -> {state["next_agent"]} \n")
    return state["next_agent"]
