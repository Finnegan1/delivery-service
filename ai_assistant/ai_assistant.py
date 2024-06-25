import os
import dataclasses
import pprint
import json

import tiktoken
import falcon
import jq
from openai import AzureOpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessage,
)
import openai_functools
import dotenv

import cnudie
import components
import features
import middleware.auth
import cnudie.retrieve
from gci.componentmodel import ComponentIdentity


def _get_component(
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
    component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
    component_name: str,
    component_version: str,
    invalid_semver_ok: bool=False,
):
    if component_version == 'greatest':
        component_version = components.greatest_version_if_none(
            component_name=component_name,
            version=None,
            version_lookup=component_version_lookup,
            version_filter=features.VersionFilter.RELEASES_ONLY,
            invalid_semver_ok=invalid_semver_ok,
        )

    return component_descriptor_lookup(ComponentIdentity(component_name, component_version))


def _text_token_count_check(query: str) -> str:
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(query))
    if num_tokens > 6000:
        return '''The result from the function was to big (to much tokens), try to
                resolve the problem in another way or inform the user.'''
    else:
        return query



class AiFunctions:
    def __init__(
        self,
        component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
        component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
        github_api_lookup,
        invalid_semver_ok: bool=False,
    ) -> None:
        self.component_descriptor_lookup = component_descriptor_lookup
        self.component_version_lookup = component_version_lookup
        self.github_api_lookup = github_api_lookup
        self.invalid_semver_ok = invalid_semver_ok

    def get_component_descriptor_information(
        self,
        component_name: str,
        component_version: str,
        jq_command: str,
    ) -> str:
        """

        Queries the component descriptor of a Component, specified through the component's name and version, then applies the jq command to trim the Component Descriptor to only the relevant infomration.

        :param component_name:  the name of the OCM Component for which the Component Descriptor should be acquired
        :type component_name: str
        :param component_version: Version of the OCM Component. It should be a string following the semantic versioning format (e.g., '2.1.1') or the string "greatest".
        :type component_version: str
        :param jq_commands: a valid jq command which specifies the exact data, which is needed from the compoennt descriptor
        :type jq_command: str
        """

        print("try to get infos")

        if component_version == 'greatest':
            component_version = components.greatest_version_if_none(
                component_name=component_name,
                version=None,
                version_lookup=self.component_version_lookup,
                version_filter=features.VersionFilter.RELEASES_ONLY,
                invalid_semver_ok=self.invalid_semver_ok,
            )

        try:
            component_descriptor = _get_component(
                component_name=component_name,
                component_version=component_version,
                component_descriptor_lookup=self.component_descriptor_lookup,
                component_version_lookup=self.component_version_lookup,
            )
            component_descriptor_dict = dataclasses.asdict(component_descriptor)
        except Exception as e:
            return f'''
                Querriing the Component Descriptor with the following Name and
                Version was not possible.

                Name: {component_name}
                Version: {component_version}

                Thrown Exception:
                    {e}
            '''

        try:
            jq_result = json.dumps(jq.compile(jq_command).input(component_descriptor_dict).all())
        except Exception as e:
            exception_string = f'''
                The selecting of the data trough the execution of jq resulted in an error in the {index + 1}. Step. The jq command was {jq_command}.
                The Error is: {e}
            '''

            if len(json.dumps(component_descriptor_dict)) < 1000:
                exception_string = f'''{exception_string}

                    The result without the jq command applied is:
                    {json.dumps(component_descriptor_dict)}
                '''

            return exception_string
        return f''' The Querie was sucessfull. The result is: {jq_result}'''


    def search_in_component_tree_by_name(
        self,
        root_component_name: str,
        root_component_version: str,
        searched_component_name: str,
    ):
        '''
        Searches within the component tree of an root_component for referenced Components by Name. Usefull for searching for deoendencies.
        :param root_component_name: Name of the Root Component.
        :type root_component_name: str
        :param root_component_version: Version of the Root Component.
        :type root_component_version: str
        :param searched_component_name: Component Name for which the Component Tree is searched trough.
        :type searched_component_name: str
        '''

        if root_component_version == 'greatest':
            root_component_version = components.greatest_version_if_none(
                component_name=root_component_name,
                version=None,
                version_lookup=self.component_version_lookup,
                version_filter=features.VersionFilter.RELEASES_ONLY,
                invalid_semver_ok=self.invalid_semver_ok,
            )

        component_dependencies = components.resolve_component_dependencies(
            component_name=root_component_name,
            component_version=root_component_version,
            component_descriptor_lookup=self.component_descriptor_lookup,
            ctx_repo=None,
        )

        filtered_component_dependencies = [
            {
                'name': component.component.name,
                'version': component.component.version,
                #'repositoryContexts': component.component.repositoryContexts,
            }
            for component
            in component_dependencies
            if component.component.name == searched_component_name
        ]
        return {'componentDependencies': filtered_component_dependencies}


    def search_in_component_tree_by_partial_name(
        self,
        root_component_name: str,
        root_component_version: str,
        searched_partial_component_name: str,
    ):
        '''
        Searches within the component tree of an root_component for referenced Components by Name. This is a partial name search, so it returns all Components for wich the searched_partial_component_name is a substring of the actual name. Usefull for searching for dependencies
        :param root_component_name: Name of the Root Component.
        :type root_component_name: str
        :param root_component_version: Version of the Root Component.
        :type root_component_version: str
        :param searched_component_name: Component Name for which the Component Tree is searched trough.
        :type searched_component_name: str
        '''

        if root_component_version == 'greatest':
            root_component_version = components.greatest_version_if_none(
                component_name=root_component_name,
                version=None,
                version_lookup=self.component_version_lookup,
                version_filter=features.VersionFilter.RELEASES_ONLY,
                invalid_semver_ok=self.invalid_semver_ok,
            )

        component_dependencies = components.resolve_component_dependencies(
            component_name=root_component_name,
            component_version=root_component_version,
            component_descriptor_lookup=self.component_descriptor_lookup,
            ctx_repo=None,
        )

        filtered_component_dependencies = [
            {
                'name': component.component.name,
                'version': component.component.version,
                #'repositoryContexts': component.component.repositoryContexts,
            }
            for component
            in component_dependencies
            if searched_partial_component_name in component.component.name
        ]
        return {'componentDependencies': filtered_component_dependencies}



class Conversation:
    def __init__(self, system_message_content: str):
        self.conversation_history: list[ChatCompletionMessage] = [{
            'role': 'system',
            'content': system_message_content
        }]
        self.total_tokens: int = 0

    def add_to_total_tokens(self, new_tokens: int):
        self.total_tokens += new_tokens

    def add_whole_message(self, message: ChatCompletionMessage):
        self.conversation_history.append(message)

    def add_user_message(self, content: str):
        self.conversation_history.append({
            'role': 'user',
            'content': content,
        })

    def add_tool_call_result_message(
        self,
        tool_call_id: str,
        function_response: str,
        function_name: str,
    ):
        self.conversation_history.append({
            'role': 'tool',
            'content': function_response,
            'tool_call_id': tool_call_id,
            'name': function_name
        })

    def add_assistent_message(self, content: str):
        self.conversation_history.append({
            'role': 'assistant',
            'content': content,
        })

    def display_conversation(self):
        for message in self.conversation_history:
            print(f"{message['role']}: {message['content']}\n\n")

    def return_last_message(self):
        last_message = self.conversation_history[-1]
        return last_message


dotenv.load_dotenv()
DEFAULT_API_VERSION = os.getenv('AZURE_OPENAI_API_VERSION')
MICROSOFT_AZURE_OPENAI_API_KEY = os.getenv('AZURE_OPENAI_API_KEY')
MICROSOFT_AZURE_OPENAI_API_ENDPOINT = os.getenv('AZURE_OPENAI_ENDPOINT')
OPEN_AI_MODEL = os.getenv('OPEN_AI_MODEL')
#'gpt-35-16k-0613'

SYSTEM_MESSAGE = '''
You are a OCM (Open Component Model) expert, you answer questions regarding general questions about OCM Components.
When answering answers you only use the information given to you in the context or call a provided function and use the result of this call.
If you are not sure or have no Data in the context and no fitting function, you answer to the User, that you can not healp him with this task, but would like to healp him if he has some other Questions.

If there are tasks, which are only possible through recursive calling of a function, do this up to 5 times!

You will be provided with a Context Component Name and Context Component Version. This is the last OCM Component, the user looked at.
Questions with unspecified Component Name and Component Version (Component ID) is porbapliy in relation to this Component.
'''

def call_openai(
    conversation: Conversation,
    openai_client: AzureOpenAI,
    ai_functions_orchestrator: openai_functools.FunctionsOrchestrator
):
    response = openai_client.chat.completions.create(
        model=OPEN_AI_MODEL,
        messages=conversation.conversation_history,
        tools=ai_functions_orchestrator.create_tools_descriptions(),
    )
    return response

def handle_response(
    response: ChatCompletion,
    conversation: Conversation,
    ai_functions_orchestrator: openai_functools.FunctionsOrchestrator,
    openai_client: AzureOpenAI,
) -> tuple[ChatCompletionMessage, int]:
    # check if the response is a function call, and if so, call the function
    # else, add the response to the conversation history and display it

    conversation.add_to_total_tokens(response.usage.total_tokens)

    if response.choices[0].finish_reason != "tool_calls":
        conversation.add_assistent_message(
            content=response.choices[0].message.content,
        )
        return (
            conversation.conversation_history[-1],
            conversation.total_tokens,
        )
    else:
        conversation.add_whole_message(message=response.choices[0].message)
        function_response = ai_functions_orchestrator.call_function(response)
        for index, tool_call_id in enumerate(function_response.keys()):
            conversation.add_tool_call_result_message(
                function_response=_text_token_count_check(str(function_response[tool_call_id])),
                tool_call_id=tool_call_id,
                function_name=response.choices[0].message.tool_calls[index].function.name
            )

        second_response = call_openai(conversation=conversation, openai_client=openai_client, ai_functions_orchestrator=ai_functions_orchestrator )

        return handle_response(
            second_response,
            conversation,
            ai_functions_orchestrator,
            openai_client
        )

@middleware.auth.noauth
class AiAssistantChat:
    def __init__(
        self,
        component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
        component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
        github_api_lookup,
        invalid_semver_ok: bool=False,
    ):

        self._component_descriptor_lookup = component_descriptor_lookup
        self._component_version_lookup = component_version_lookup
        self.github_api_lookup = github_api_lookup
        self.openai_client = AzureOpenAI(
            api_key=MICROSOFT_AZURE_OPENAI_API_KEY,
            azure_endpoint=MICROSOFT_AZURE_OPENAI_API_ENDPOINT,
            api_version=DEFAULT_API_VERSION,
        )
        self.invalid_semver_ok = invalid_semver_ok

    def on_get(self, req: falcon.Request, resp: falcon.Response):

        ai_functions = AiFunctions(
            component_descriptor_lookup=self._component_descriptor_lookup,
            component_version_lookup=self._component_version_lookup,
            github_api_lookup=self.github_api_lookup
        )
        ai_functions_orchestrator = openai_functools.FunctionsOrchestrator()
        ai_functions_orchestrator.register_all([
            ai_functions.get_component_descriptor_information,
            ai_functions.search_in_component_tree_by_name,
            ai_functions.search_in_component_tree_by_partial_name,
        ])


        question: str = req.get_param(
            name="question",
            required=True,
        )
        context_component_identity_str: str = req.get_param(
            name='contextComponentIdentity',
            required=True,
        )
        context_component_identity: ComponentIdentity = ComponentIdentity(
            name=context_component_identity_str.split(":")[0],
            version=context_component_identity_str.split(":")[1],
        )

        conversation = Conversation(
            system_message_content=SYSTEM_MESSAGE,
        )
        conversation.add_user_message(content=step_by_step_task(question=question, context_component_identity=context_component_identity))

        response: ChatCompletion = self.openai_client.chat.completions.create(
            messages=conversation.conversation_history,
            model=OPEN_AI_MODEL,
            tools=ai_functions_orchestrator.create_tools_descriptions()
        )

        print(response.usage.total_tokens)


        (answer, used_tokens) = handle_response(response=response, conversation=conversation, ai_functions_orchestrator=ai_functions_orchestrator, openai_client=self.openai_client)
        print(used_tokens)

        resp.media = answer['content']
