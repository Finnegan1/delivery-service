import langchain_openai
import langchain_core.prompts
import gci.componentmodel
import ai_assistant.ai_tools
import ai_assistant.graph_state

class PlanningAgent:
    def __init__(
        self,
        root_component_identity: gci.componentmodel.ComponentIdentity,
        members: list[str]
    ):
        llm =  langchain_openai.AzureChatOpenAI(
            model='gpt-40-128k-1106'
        )

        chat_template = [
            ("system", "You are part of a larger team of agents, each with a specific role in answering a user's question. As the 'planning_agent', your responsibility is to plan individual tasks for the other agents. These tasks may build upon each other and should ultimately lead to the answer to the user's question. Your plan will be handed over to a 'supervisor_agent' who will delegate tasks based on your plan to the following members:"),

            ("system", "## ocm_agent: This agent is an expert on OCM Components. Its capabilities include: \n- Retrieving specific information about a particular OCM Component (e.g., name or dependencies) \n- Searching through the dependency tree of a specific OCM Component by name or partial name"),

            ("system", "## security_agent: This agent specializes in vulnerabilities, malware, and licenses. It can: \n- Search for malware findings for a specific component \n- Search for vulnerability findings for a specific component \n- Search for license findings for a specific component \n- Get dependencies with vulnerabilitity of a specific component"),

            ("system", "Your task is to be as precise and brief as possible, eliminating unnecessary steps. Not all members need to be included in your plan at all times."),

            ("system", "The Delivery Gear is an application that provides various information about OCM Components. Within the application, a root component is always selected. The current selected root component is: \n<root_component_name>{root_component_name}</root_component_name> \n<root_component_version>{root_component_version}</root_component_version> \nUsers can also ask questions about other Components, not necessarily within the current dependency tree of the root Component. The root component information is provided as a reference and does not necessarily relate to the user's request."),

            ("system", "Given the conversation above, create a step-by-step plan of tasks for the supervisor to execute or delegate. Always double-check to ensure all steps are necessary and as precise as possible. Ask yourself if each step is truly necessary."),

            ("system", "It is always better not to answer a question then answer it the wrong way! If you dont know an important thing, express this and dont make something up!"),

            ('human', '{question}')
        ]

        assistant_prompt = langchain_core.prompts.ChatPromptTemplate.from_messages(chat_template).partial(
            root_component_name=root_component_identity.name,
            root_component_version=root_component_identity.version
        )

        supervisor_chain = (
            assistant_prompt
            | llm
        )

        self.runnable = supervisor_chain

    def __call__(
        self,
        state: ai_assistant.graph_state.State
    ) -> ai_assistant.graph_state.State:
        llm_message = self.runnable.invoke({
            'question': state['question']
        })
        return {
            'current_plan': llm_message.content,
            'agent_messages': [],
            'agent_task': '',
            'question': state['question'],
        }
