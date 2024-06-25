import langchain
import langchain_core.runnables
import langgraph.prebuilt
import langgraph.prebuilt.tool_node
import langchain_core.messages
import langgraph.utils
import typing
import langchain_core.messages.tool
import langchain_core.messages.ai
import langchain_core.runnables
import langchain.tools
import langchain_core.messages.utils
import langchain_core.tools
import langchain_core.runnables.config
import asyncio
import ai_assistant.graph_state

def handle_tool_error(state) -> dict:
    error = state.get("error")
    tool_calls = state["agent_messages"][-1].tool_calls
    return {
        "agent_messages":
            state["agent_messages"] +
            [
                langchain_core.messages.ToolMessage(
                    content=f"Error: {repr(error)}\n please fix your mistakes.",
                    tool_call_id=tc["id"],
                )
                for tc in tool_calls
            ]
    }

def create_tool_node_with_fallback(tools: list[langchain.tools.BaseTool]) -> langchain_core.runnables.RunnableWithFallbacks:
    return ToolNode(tools).with_fallbacks(
        [langchain_core.runnables.RunnableLambda(handle_tool_error)], exception_key="error"
    )

class ToolNode(langgraph.utils.RunnableCallable):
    """
    A node that runs the tools requested in the last AIMessage. It can be used
    either in StateGraph with a "messages" key or in MessageGraph. If multiple
    tool calls are requested, they will be run in parallel. The output will be
    a list of ToolMessages, one for each tool call.
    """

    def __init__(
        self,
        tools: typing.Sequence[typing.Union[langchain.tools.BaseTool, typing.Callable]],
        *,
        name: str = "tools",
        tags: typing.Optional[list[str]] = None,
    ) -> None:
        super().__init__(self._func, self._afunc, name=name, tags=tags, trace=False)
        self.tools_by_name: typing.Dict[str, langchain.tools.BaseTool] = {}
        for tool_ in tools:
            if not isinstance(tool_, langchain.tools.BaseTool):
                tool_ = langchain_core.tools.tool(tool_)
            self.tools_by_name[tool_.name] = tool_

    def _func(
        self, state: ai_assistant.graph_state.State, config: langchain_core.runnables.RunnableConfig
    ) -> typing.Any:

        if agent_messages := state.get("agent_messages", []):
            output_type = "dict"
            last_agent_message = agent_messages[-1]
        else:
            raise ValueError("No message found in input")

        if not isinstance(last_agent_message, langchain_core.messages.ai.AIMessage):
            raise ValueError("Last message is not an AIMessage")

        def run_one(call:  langchain_core.messages.tool.ToolCall):
            output = self.tools_by_name[call["name"]].invoke(call["args"], config)
            return  langchain_core.messages.tool.ToolMessage(
                content=langgraph.prebuilt.tool_node.str_output(output), name=call["name"], tool_call_id=call["id"]
            )

        with langchain_core.runnables.config.get_executor_for_config(config) as executor:
            outputs = [*executor.map(run_one, last_agent_message.tool_calls)]
            if output_type == "list":
                return outputs
            else:
                return {"agent_messages": state['agent_messages'] + outputs}


    async def _afunc(
        self, state: ai_assistant.graph_state.State, config: langchain_core.runnables.RunnableConfig
    ) -> typing.Any:

        if agent_messages := state.get("agent_messages", []):
            output_type = "dict"
            last_agent_message = agent_messages[-1]
        else:
            raise ValueError("No message found in input")

        if not isinstance(last_agent_message, langchain_core.messages.ai.AIMessage):
            raise ValueError("Last message is not an AIMessage")

        async def run_one(call: langchain_core.messages.tool.ToolCall):
            output = await self.tools_by_name[call["name"]].ainvoke(
                call["args"], config
            )
            return langchain_core.messages.tool.ToolMessage(
                content=langgraph.prebuilt.tool_node.str_output(output), name=call["name"], tool_call_id=call["id"]
            )

        outputs = await asyncio.gather(*(run_one(call) for call in last_agent_message.tool_calls))
        if output_type == "list":
            return outputs
        else:
            return {"agent_messages": state['agent_messages'] + outputs}
