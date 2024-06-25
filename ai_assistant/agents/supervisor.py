import langchain_openai
import langchain_core.prompts
import langchain_core.messages
import ai_assistant.ai_assistant
import ai_assistant.ai_tools
import gci.componentmodel
import langchain_core.output_parsers.openai_functions
import ai_assistant.graph_state
import langchain_core.pydantic_v1

class LlmAnswer(langchain_core.pydantic_v1.BaseModel):
    next: str = langchain_core.pydantic_v1.Field(description="Next Agent to be called.")
    task: str = langchain_core.pydantic_v1.Field(description="Task the next Agent has to solve.")

class SupervisorAgent:
    def __init__(
        self,
        root_component_identity: gci.componentmodel.ComponentIdentity,
        members: list[str]
    ):
        llm =  langchain_openai.AzureChatOpenAI(
            model='gpt-40-128k-1106',
            model_kwargs={"response_format": {"type": "json_object"}},
        )

        routing_options = members

        parser = langchain_core.output_parsers.JsonOutputParser(pydantic_object=LlmAnswer)

        assistant_prompt = langchain_core.prompts.ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a supervisor who is tasked with managing a conversation between the"
                    " following workers: {members}"
                    " Your aim is to implement the individual steps of the planner as best you can,"
                    " step by step, using the means at your disposal. "
                    " Your goal is it to be able to route to the 'FINISH' node with a valid answer to the following question through implementing the plan:"
                    " {question}"
                    " "
                    " \nWithin the application, there is always a root component selected. Currently the following one is selected:"
                    "   <root_component_name>{root_component_name}</root_component_name>"
                    "   <root_component_version>{root_component_version}</root_component_version>"
                    " "
                    " Respond with the following json structure:"
                    " {format_instructions}"
                    " Respond with the worker to act next in the next field and the task he should solve in the task filed."
                    " The worker will try to solve your task in"
                    " the best possible way and respond with their results and status."
                    " When finished route to the summary_agent trough the next field."
                ),
                ("system", "It is always better not to answer a question then answer it the wrong way! If you dont know an important thing, express this and dont make something up!"),
                (
                    "system",
                    "The current plan looks the following:"
                    " {current_plan}"
                    " \n"
                    " You have already done the following Steps with the following results:"
                    " {executed_tasks_results}"
                ),
                (
                    "system",
                    "Given the executed tasks above, who should act next and on which task?"
                    " Are the infrmation from the already executed steps enough to answer the question '{question}'?"
                    " If yes route to 'summary_agent'"
                    " Else choose one of other members to give a task to."
                    " Select one of: {members}"
                )
            ]
        ).partial(
            routing_options=str(routing_options),
            members=", ".join(members),
            root_component_name=root_component_identity.name,
            root_component_version=root_component_identity.version,
            format_instructions=parser.get_format_instructions(),
        )

        supervisor_chain = (
            assistant_prompt
            | llm
            | parser
        )

        self.runnable = supervisor_chain

    def __call__(self, state: ai_assistant.graph_state.State) -> ai_assistant.graph_state.State:
        executed_tasks_results = state.get('executed_tasks_results', {}) or {}
        if executed_tasks_results:
            executed_tasks_results = ' \n '.join([f'Task-{index}: {item[0]}, Result-{index}: {item[1]}' for index, item in enumerate(executed_tasks_results.items())])
        else:
            executed_tasks_results = ''
        llm_message: LlmAnswer = self.runnable.invoke({
            'current_plan': state["current_plan"],
            'executed_tasks_results': executed_tasks_results,
            'question': state['question'],
        })

        return {
            'next_agent': llm_message['next'],
            'agent_task': llm_message['task'],
            'agent_messages': [],
            'current_plan': state['current_plan'],
            'executed_tasks_results': state.get('executed_tasks_results', {}),
            'question': state['question'],
            'answer': state['answer'],
        }
