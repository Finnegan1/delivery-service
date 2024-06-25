import ai_assistant.graph_state
import langchain_openai
import langchain_core.output_parsers
import langchain_core.prompts

class AgentCleanup:
    def __init__(
        self,
    ):
        llm =  langchain_openai.AzureChatOpenAI(
            model='gpt-40-128k-1106',
        )

        assistant_prompt = langchain_core.prompts.ChatPromptTemplate.from_messages(
            [
                (
                    "human",
                    "Your are part of a team of several agents. The agent {next_agent} had the following task:"
                    " {agent_task}"
                    " You can see his steps in the following messages. Please summerize the result, so that the question/task he had to"
                    " fullfill is fullfilled. Only use the data from the messages! Dont make something up. It also can happen, that the task was nor fulliflled."
                ),
                (
                    "placeholder",
                    "{agent_messages}"
                )
            ]
        )

        supervisor_chain = (
            assistant_prompt
            | llm
        )

        self.runnable = supervisor_chain

    def __call__(
        self,
        state: ai_assistant.graph_state.State,
    ) -> ai_assistant.graph_state.State:
        llm_message = self.runnable.invoke({
            'next_agent': state['next_agent'],
            'agent_task': state['agent_task'],
            'agent_messages': state.get('agent_messages', []),
        })
        executed_tasks_results = state['executed_tasks_results'] or {}
        executed_tasks_results[state['agent_task']] = llm_message.content
        return {
            'next_agent': 'supervisor_agent',
            'agent_task': state['agent_task'],
            'agent_messages': [],
            'executed_tasks_results': executed_tasks_results,
            'current_plan': state['current_plan'],
            'answer': state['answer'],
            'question': state['question'],
        }

class SummaryAgent:
    def __init__(
        self,
    ):
        llm =  langchain_openai.AzureChatOpenAI(
            model='gpt-35-16k-0613',
        )

        assistant_prompt = langchain_core.prompts.ChatPromptTemplate.from_messages(
            [
                (
                    "human",
                    "Your are part of a team of several agents which try to anser the following question: {question}."
                    " Based in the plan, the planner_agent created the following plan:"
                    " {current_plan}"
                    " The supervisor instructed the memebrs to fullfill different tasks. They are lited with the result:"
                    " {executed_tasks_results}"
                    " Please answer the question with the help of the executed tasks and their results."
                    " Be precise! Answer as good as possible to the user. The answer should be fitting to the users question. Not too short, not too long."
                    " Format in propper MarkDown!"
                ),
                (
                    "placeholder",
                    "{agent_messages}"
                )
            ]
        )

        supervisor_chain = (
            assistant_prompt
            | llm
        )

        self.runnable = supervisor_chain

    def __call__(
        self,
        state: ai_assistant.graph_state.State,
    ) -> ai_assistant.graph_state.State:

        executed_tasks_results = state.get('executed_tasks_results', {}) or {}
        if executed_tasks_results:
            executed_tasks_results = ' \n '.join([f'Task: {key}, Result: {val}' for key, val in executed_tasks_results.items()])
        else:
            executed_tasks_results = ''
        llm_message: str = self.runnable.invoke({
            'current_plan': state["current_plan"],
            'executed_tasks_results': executed_tasks_results,
            'question': state['question'],
        }).content

        return {
            'next_agent': 'supervisor_agent',
            'agent_task': state['agent_task'],
            'agent_messages': [],
            'executed_tasks_results': state['executed_tasks_results'],
            'current_plan': state['current_plan'],
            'question': state['question'],
            'answer': llm_message,
        }
