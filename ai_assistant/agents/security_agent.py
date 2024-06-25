import gci.componentmodel
import langchain_core.runnables
import langchain_core.prompts
from ai_assistant import ai_tools
import ai_assistant.graph_state
import langchain_core.messages
import langchain_openai
import cnudie.retrieve
import ai_assistant.ai_assistant
import sqlalchemy.orm.session


class SecurityAgent:
    def __init__(
        self,
        component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
        component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
        github_api_lookup,
        root_component_identity: gci.componentmodel.ComponentIdentity,
        db_session: sqlalchemy.orm.session.Session,
        invalid_semver_ok: bool=False,
    ) -> None:
        llm =  langchain_openai.AzureChatOpenAI(
            model='gpt-40-128k-1106'
        )
        assistant_prompt = langchain_core.prompts.ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful security agent helping with questions, regarding security questions regarding vulnerbilities, malware and licenses."
                    " You have access to different tools, which enable you to access a big Database which holds entries of these information in connection with different OCM Components."
                    " These Information are often the result form Scannes, which are done within the delivery Gear."
                    " The Delivery Gear is an application, which healps to get an overview about OCM components as well as scann these for vulnerbilities, malware and licenses."
                    " Use the provided tools to get the infomration to solve you task."
                ),
                (
                    'human',
                    'Solve the following task with the help of the tools, which are available to you!'
                    '{agent_task}'
                ),
                ('placeholder', '{agent_messages}'),
                (
                    'system',
                    'If these information are enough to answer the question, please answer the question without calling a new tool. If you still need more information, call a tool.s'
                )
            ]
        ).partial(
            root_component_name=root_component_identity.name,
            root_component_version=root_component_identity.version,
        )

        vulnerability_tools = ai_tools.get_vulnerability_tools(
            db_session=db_session,
            component_descriptor_lookup=component_descriptor_lookup,
            component_version_lookup=component_version_lookup,
            github_api_lookup=github_api_lookup,
            invalid_semver_ok=invalid_semver_ok,
        )

        malware_tools = ai_tools.get_malware_tools(
            db_session=db_session,
            component_descriptor_lookup=component_descriptor_lookup,
            component_version_lookup=component_version_lookup,
            github_api_lookup=github_api_lookup,
            invalid_semver_ok=invalid_semver_ok,
        )

        license_tools = ai_tools.get_license_tools(
            db_session=db_session,
            component_descriptor_lookup=component_descriptor_lookup,
            component_version_lookup=component_version_lookup,
            github_api_lookup=github_api_lookup,
            invalid_semver_ok=invalid_semver_ok,
        )

        self.runnable = assistant_prompt | llm.bind_tools(vulnerability_tools + malware_tools + license_tools)

    def __call__(self, state: ai_assistant.graph_state.State) -> ai_assistant.graph_state.State:
        llm_message = self.runnable.invoke({
            'agent_task': state['agent_task'],
            'agent_messages': state['agent_messages'],
        })
        return {
            'agent_messages': state['agent_messages'] + [llm_message],
            'next_agent': 'security_agent',
            'agent_task': state['agent_task'],
            'answer': state['answer'],
            'current_plan': state['current_plan'],
            'question': state['question'],
            'executed_tasks_results': state['executed_tasks_results'],
        }
