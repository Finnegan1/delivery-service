import os
import dataclasses
import pprint
import json
from ci.util import verbose
from langchain_core.prompts import ChatPromptTemplate

import falcon
import jq
import langchain
import langchain.agents
import langchain.prompts
import langchain_core
import langchain_core.prompts
import langchain_core.messages
import langchain_core.messages.system
import langchain.memory.buffer
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI
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
        print("try to get infos")

        if component_version == 'greatest' or component_version == '':
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
                The selecting of the data trough the execution of jq resulted in an Error. The jq command was {jq_command}.
                The Error is: {e}
            '''
            
            if len(json.dumps(component_descriptor_dict)) < 1000:
                exception_string = f'''{exception_string}

                    The result without the jq command applied is:
                    {json.dumps(component_descriptor_dict)}
                '''

            return exception_string
        print(f''' The Querie was sucessfull. The result is: {jq_result}''')
        return f''' The Querie was sucessfull. The result of the jq comman {jq_command} on the Component Descriptor "{component_name}" version "{component_version}" is: 
            {jq_result}
        ''' 


    def search_in_component_tree_by_name(
        self,
        root_component_name: str,
        root_component_version: str,
        searched_component_name: str,
    ) -> dict[str, list[dict[str, str]]]:

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
        return f'''
        The fuzzy search resulted in the following Components, take in calculation that it only was a fuzzy search, so check if all of these components fit your wishes and needs to answer the question. Else filter!
         
        Found Components: 
        {filtered_component_dependencies}
        '''

dotenv.load_dotenv()      
DEFAULT_API_VERSION = os.getenv('DEFAULT_API_VERSION')
MICROSOFT_AZURE_OPENAI_API_KEY = os.getenv('MICROSOFT_AZURE_OPENAI_API_KEY')
MICROSOFT_AZURE_OPENAI_API_ENDPOINT = os.getenv('MICROSOFT_AZURE_OPENAI_API_ENDPOINT')
OPEN_AI_MODEL = os.getenv('OPEN_AI_MODEL')
#'gpt-35-16k-0613'


@middleware.auth.noauth 
class AiAssistantChatLC:
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
        self.invalid_semver_ok = invalid_semver_ok

        ai_functions = AiFunctions(
            component_descriptor_lookup=self._component_descriptor_lookup,
            component_version_lookup=self._component_version_lookup,
            github_api_lookup=self.github_api_lookup 
        )
        
        @tool
        def get_component_descriptor_information(component_name: str, component_version:str, jq_command: str):
            '''
            Queries the component descriptor of a Component, specified through the component's name and version, then applies the jq command to trim the Component Descriptor to only the relevant information.
            
            Args:
                component_name (str): The name of the OCM Component for which the Component Descriptor should be acquired.
                component_version (str): Version of the OCM Component. It should be a string following the semantic versioning format (e.g., '2.1.1') or the string "greatest".
                jq_command (str): A valid jq command which specifies the exact data, which is needed from the component descriptor.
            '''
            return ai_functions.get_component_descriptor_information(
                component_name=component_name,
                component_version=component_version,
                jq_command=jq_command,
            )

        @tool
        def search_in_component_tree_by_name(
            root_component_name: str,
            root_component_version: str,
            searched_component_name: str,
        ) -> dict[str, list[dict[str, str]]]:
            '''
            Function to search within the component tree of an root component for referenced Components by Name. This is useful when searching for dependencies.
            
            Args:
                root_component_name (str): Name of the Root Component.  
                root_component_version (str): Version of the Root Component. 
                searched_component_name (str): Component Name for which the Component Tree is searched through.
            
            Returns:
                dict: A dictionary with a key as 'dependencies' and value as a list of dictionaries. Each dictionary in the list represents a dependency with its name and version.
            '''
            return ai_functions.search_in_component_tree_by_name(
               root_component_name=root_component_name,
               root_component_version=root_component_version,
               searched_component_name=searched_component_name,
            )

        @tool
        def search_in_component_tree_by_partial_name(
            root_component_name: str,
            root_component_version: str,
            searched_partial_component_name: str,
        ) -> str:
            '''
            Function to partially search within the component tree of a root component for referenced Components by Name. It returns all Components for which the searched_partial_component_name is a substring of the actual name. This is especially useful when searching for dependencies.
            Args:
                root_component_name (str): Name of the Root Component.
                root_component_version (str): Version of the Root Component.
                searched_component_name (str): Partial component name for which the Component Tree is searched.
            Returns:
                str: A dictionary with a key as 'dependencies' and value as a list of dictionaries. Each dictionary in the list holds found dependencies with their names and versions.
            '''
            return ai_functions.search_in_component_tree_by_partial_name(
               root_component_name=root_component_name,
               root_component_version=root_component_version,
               searched_partial_component_name=searched_partial_component_name,
            )



        self.ai_tools = [get_component_descriptor_information, search_in_component_tree_by_name, search_in_component_tree_by_partial_name]


        self.openai_model = AzureChatOpenAI(
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
            model=os.getenv('OPEN_AI_MODEL'),
            api_version=os.getenv('AZURE_OPENAI_API_VERSION'),
        )


    def on_get(self, req: falcon.Request, resp: falcon.Response):

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

        prompt = langchain.prompts.ChatPromptTemplate.from_messages([
            langchain_core.messages.system.SystemMessage(
                content='''
                    # Your Role:
                    You are a OCM (Open Component Model) assistant. You answer questions regarding general questions about OCM Components.
                    When answering answers you only use the information given to you in the context or call a provided function and use the result of this call.
                    If you are not sure or have no Data in the context and no fitting function, you answer to the User, that you can not healp him with this task, but would like to healp him if he has some other Questions.
                    
                    # Context Information:
                    You will be provided with a Context Component Name and Context Component Version. This is the last OCM Component, the user looked at. 
                    Questions with unspecified Component Name and Component Version (Component ID) is porbapliy in relation to this Component.
                    
                    # General Knowledge usefull for sucess:
                    - When calling functions, always keep in mind the following structure of a Component Descriptor:
                        - {"{\"$id\":\"https://gardener.cloud/schemas/component-descriptor-v2\",\"$schema\":\"https://json-schema.org/draft/2020-12/schema\",\"description\":\"Gardener Component Descriptor v2 schema\",\"definitions\":{\"meta\":{\"type\":\"object\",\"description\":\"component descriptor metadata\",\"required\":[\"schemaVersion\"],\"properties\":{\"schemaVersion\":{\"type\":\"string\"}}},\"label\":{\"type\":\"object\",\"required\":[\"name\",\"value\"]},\"componentName\":{\"type\":\"string\",\"maxLength\":255,\"pattern\":\"^[a-z0-9.\\\\-]+[.][a-z][a-z]+/[-a-z0-9/_.]*$\"},\"identityAttributeKey\":{\"minLength\":2,\"pattern\":\"^[a-z0-9]([-_+a-z0-9]*[a-z0-9])?$\"},\"relaxedSemver\":{\"pattern\":\"^[v]?(0|[1-9]\\\\d*)(?:\\\\.(0|[1-9]\\\\d*))?(?:\\\\.(0|[1-9]\\\\d*))?(?:-((?:0|[1-9]\\\\d*|\\\\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\\\\.(?:0|[1-9]\\\\d*|\\\\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\\\\+([0-9a-zA-Z-]+(?:\\\\.[0-9a-zA-Z-]+)*))?$\",\"type\":\"string\"},\"identityAttribute\":{\"type\":\"object\",\"propertyNames\":{\"$ref\":\"#/definitions/identityAttributeKey\"}},\"repositoryContext\":{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{\"type\":{\"type\":\"string\"}}},\"ociRepositoryContext\":{\"allOf\":[{\"$ref\":\"#/definitions/repositoryContext\"},{\"required\":[\"baseUrl\"],\"properties\":{\"baseUrl\":{\"type\":\"string\"},\"type\":{\"type\":\"string\"}}}]},\"access\":{\"type\":\"object\",\"description\":\"base type for accesses (for extensions)\",\"required\":[\"type\"]},\"githubAccess\":{\"type\":\"object\",\"required\":[\"type\",\"repoUrl\",\"ref\"],\"properties\":{\"type\":{\"type\":\"string\",\"enum\":[\"github\"]},\"repoUrl\":{\"type\":\"string\"},\"ref\":{\"type\":\"string\"},\"commit\":{\"type\":\"string\"}}},\"noneAccess\":{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{\"type\":{\"type\":\"string\",\"enum\":[\"None\"]}}},\"sourceDefinition\":{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{\"name\":{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"},\"extraIdentity\":{\"$ref\":\"#/definitions/identityAttribute\"},\"version\":{\"$ref\":\"#/definitions/relaxedSemver\"},\"type\":{\"type\":\"string\"},\"labels\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/label\"}},\"access\":{\"anyOf\":[{\"$ref\":\"#/definitions/access\"},{\"$ref\":\"#/definitions/githubAccess\"},{\"$ref\":\"#/definitions/httpAccess\"}]}}},\"digestSpec\":{\"type\":\"object\",\"required\":[\"hashAlgorithm\",\"normalisationAlgorithm\",\"value\"],\"properties\":{\"hashAlgorithm\":{\"type\":\"string\"},\"normalisationAlgorithm\":{\"type\":\"string\"},\"value\":{\"type\":\"string\"}}},\"signatureSpec\":{\"type\":\"object\",\"required\":[\"algorithm\",\"value\",\"mediaType\"],\"properties\":{\"algorithm\":{\"type\":\"string\"},\"value\":{\"type\":\"string\"},\"mediaType\":{\"description\":\"The media type of the signature value\",\"type\":\"string\"}}},\"signature\":{\"type\":\"object\",\"required\":[\"name\",\"digest\",\"signature\"],\"properties\":{\"name\":{\"type\":\"string\"},\"digest\":{\"$ref\":\"#/definitions/digestSpec\"},\"signature\":{\"$ref\":\"#/definitions/signatureSpec\"}}},\"srcRef\":{\"type\":\"object\",\"description\":\"a reference to a (component-local) source\",\"properties\":{\"identitySelector\":{\"$ref\":\"#/definitions/identityAttribute\"},\"labels\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/label\"}}}},\"componentReference\":{\"type\":\"object\",\"description\":\"a reference to a component\",\"required\":[\"name\",\"componentName\",\"version\"],\"properties\":{\"componentName\":{\"$ref\":\"#/definitions/componentName\"},\"name\":{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"},\"extraIdentity\":{\"$ref\":\"#/definitions/identityAttribute\"},\"version\":{\"$ref\":\"#/definitions/relaxedSemver\"},\"labels\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/label\"}},\"digest\":{\"oneOf\":[{\"type\":\"null\"},{\"$ref\":\"#/definitions/digestSpec\"}]}}},\"resourceType\":{\"type\":\"object\",\"description\":\"base type for resources\",\"required\":[\"name\",\"version\",\"type\",\"relation\",\"access\"],\"properties\":{\"name\":{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"},\"extraIdentity\":{\"$ref\":\"#/definitions/identityAttribute\"},\"version\":{\"$ref\":\"#/definitions/relaxedSemver\"},\"type\":{\"type\":\"string\"},\"srcRefs\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/srcRef\"}},\"relation\":{\"type\":\"string\",\"enum\":[\"local\",\"external\"]},\"labels\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/label\"}},\"access\":{\"anyOf\":[{\"$ref\":\"#/definitions/access\"},{\"$ref\":\"#/definitions/ociBlobAccess\"},{\"$ref\":\"#/definitions/localFilesystemBlobAccess\"},{\"$ref\":\"#/definitions/localOciBlobAccess\"}]},\"digest\":{\"oneOf\":[{\"type\":\"null\"},{\"$ref\":\"#/definitions/digestSpec\"}]}}},\"ociImageAccess\":{\"type\":\"object\",\"required\":[\"type\",\"imageReference\"],\"properties\":{\"type\":{\"type\":\"string\",\"enum\":[\"ociRegistry\"]},\"imageReference\":{\"type\":\"string\"}}},\"ociBlobAccess\":{\"type\":\"object\",\"required\":[\"type\",\"layer\"],\"properties\":{\"type\":{\"type\":\"string\",\"enum\":[\"ociBlob\"]},\"ref\":{\"description\":\"A oci reference to the manifest\",\"type\":\"string\"},\"mediaType\":{\"description\":\"The media type of the object this access refers to\",\"type\":\"string\"},\"digest\":{\"description\":\"The digest of the targeted content\",\"type\":\"string\"},\"size\":{\"description\":\"The size in bytes of the blob\",\"type\":\"number\"}}},\"localFilesystemBlobAccess\":{\"type\":\"object\",\"required\":[\"type\",\"filename\"],\"properties\":{\"type\":{\"type\":\"string\",\"enum\":[\"localFilesystemBlob\"]},\"filename\":{\"description\":\"filename of the blob that is located in the \\\"blobs\\\" directory\",\"type\":\"string\"}}},\"localOciBlobAccess\":{\"type\":\"object\",\"required\":[\"type\",\"filename\"],\"properties\":{\"type\":{\"type\":\"string\",\"enum\":[\"localOciBlob\"]},\"digest\":{\"description\":\"digest of the layer within the current component descriptor\",\"type\":\"string\"}}},\"ociImageResource\":{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{\"name\":{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"},\"extraIdentity\":{\"$ref\":\"#/definitions/identityAttribute\"},\"version\":{\"$ref\":\"#/definitions/relaxedSemver\"},\"type\":{\"type\":\"string\",\"enum\":[\"ociImage\"]},\"labels\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/label\"}},\"access\":{\"$ref\":\"#/definitions/ociImageAccess\"},\"digest\":{\"oneOf\":[{\"type\":\"null\"},{\"$ref\":\"#/definitions/digestSpec\"}]}}},\"httpAccess\":{\"type\":\"object\",\"required\":[\"type\",\"url\"],\"properties\":{\"type\":{\"type\":\"string\",\"enum\":[\"http\"]},\"url\":{\"type\":\"string\"}}},\"genericAccess\":{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{\"type\":{\"type\":\"string\",\"enum\":[\"generic\"]}}},\"genericResource\":{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{\"name\":{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"},\"extraIdentity\":{\"$ref\":\"#/definitions/identityAttribute\"},\"version\":{\"$ref\":\"#/definitions/relaxedSemver\"},\"type\":{\"type\":\"string\",\"enum\":[\"generic\"]},\"labels\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/label\"}},\"access\":{\"$ref\":\"#/definitions/genericAccess\"},\"digest\":{\"oneOf\":[{\"type\":\"null\"},{\"$ref\":\"#/definitions/digestSpec\"}]}}},\"component\":{\"type\":\"object\",\"description\":\"a component\",\"required\":[\"name\",\"version\",\"repositoryContexts\",\"provider\",\"sources\",\"componentReferences\",\"resources\"],\"properties\":{\"name\":{\"$ref\":\"#/definitions/componentName\"},\"version\":{\"$ref\":\"#/definitions/relaxedSemver\"},\"repositoryContexts\":{\"type\":\"array\",\"items\":{\"anyOf\":[{\"$ref\":\"#/definitions/ociRepositoryContext\"}]}},\"provider\":{\"type\":\"string\"},\"labels\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/label\"}},\"sources\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/sourceDefinition\"}},\"componentReferences\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/componentReference\"}},\"resources\":{\"type\":\"array\",\"items\":{\"anyOf\":[{\"$ref\":\"#/definitions/resourceType\"},{\"$ref\":\"#/definitions/ociImageResource\"},{\"$ref\":\"#/definitions/genericResource\"}]}}},\"componentReferences\":{}}},\"type\":\"object\",\"required\":[\"meta\",\"component\"],\"properties\":{\"meta\":{\"$ref\":\"#/definitions/meta\"},\"component\":{\"$ref\":\"#/definitions/component\"},\"signatures\":{\"type\":\"array\",\"items\":{\"$ref\":\"#/definitions/signature\"}}}}"}
                    - A Component name is created in the following format: <version control domain>/<organization or user>/<ropository>. e.g.: github.com/gardener/dashboard
                        - Colloquially, users sometimes name the components only after the repository or a combination of organization and repository. 
                            - e.g. "Gardener" == github.com/gardener/gardener
                            - e.g. "Gardener Dashboard" == github.com/gardener/dashboard

                '''
            ),
            langchain.prompts.MessagesPlaceholder("chat_history", optional=True),
            ('human', '''

             # Current Context Information:
                - Name of the conext Compoent = {context_component_identity_name}
                - Version of the context Component = {context_component_identity_version}

             # User input: {input}
             '''),
            langchain.prompts.MessagesPlaceholder("agent_scratchpad")
        ])

        ocm_agent = langchain.agents.create_openai_tools_agent(
            llm=self.openai_model,
            tools=self.ai_tools,
            prompt=prompt,
        )

        memory = langchain.memory.buffer.ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            input_key="input",
            output_key="output",
        )

        ocm_agent_executor = langchain.agents.AgentExecutor(
            memory=memory,
            agent=ocm_agent,
            tools=self.ai_tools,
            verbose=True,
        )

        output = ocm_agent_executor.invoke({
            "input": question,
            "context_component_identity_name": context_component_identity.name,
            "context_component_identity_version": context_component_identity.version,
        })

        resp.media = output['output']
