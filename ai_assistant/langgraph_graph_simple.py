import cnudie.retrieve
import langgraph.graph
import langgraph.prebuilt
import ai_assistant.agents.planning_agent
import ai_assistant.agents.ocm_agent
import ai_assistant.agents.security_agent
import ai_assistant.utils
import ai_assistant.ai_tools
import langgraph.checkpoint.sqlite
import gci.componentmodel
import ai_assistant.edges
import sqlalchemy.orm.session
import ai_assistant.nodes
import langchain_core.prompts
import langchain_openai
import typing
import typing_extensions
import langchain
import langchain_core.runnables
import langgraph.prebuilt.tool_node
import langchain_core.messages
import langgraph.utils
import langchain_core.messages.tool
import langchain_core.messages.ai
import langchain.tools
import langchain_core.messages.utils
import langchain_core.tools
import langchain_core.runnables.config
import asyncio
import ai_assistant.graph_state
import langgraph.graph.message

# #####
# State
# #####

class State(
    typing_extensions.TypedDict
):
    old_chat: list[langchain_core.messages.MessageLikeRepresentation]
    messages: typing.Annotated[list[langchain_core.messages.MessageLikeRepresentation], langgraph.graph.message.add_messages]
    current_plan: str
    question: str
    answer: str

# ######
# Agents
# ######

class PlanningAgent:
    def __init__(
        self,
        root_component_identity: gci.componentmodel.ComponentIdentity,
        component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
        component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
        github_api_lookup,
        db_session: sqlalchemy.orm.session.Session,
        invalid_semver_ok: bool=False,
    ):
        llm =  langchain_openai.AzureChatOpenAI(
            model='gpt-40-128k-1106'
        ).bind_tools(
            [
                *ai_assistant.ai_tools.get_ocm_tools(
                    db_session=db_session,
                    component_descriptor_lookup=component_descriptor_lookup,
                    component_version_lookup=component_version_lookup,
                    github_api_lookup=github_api_lookup,
                    invalid_semver_ok=invalid_semver_ok,
                ),
                *ai_assistant.ai_tools.get_license_tools(
                    db_session=db_session,
                    component_descriptor_lookup=component_descriptor_lookup,
                    component_version_lookup=component_version_lookup,
                    github_api_lookup=github_api_lookup,
                    invalid_semver_ok=invalid_semver_ok,
                ),
                *ai_assistant.ai_tools.get_malware_tools(
                    db_session=db_session,
                    component_descriptor_lookup=component_descriptor_lookup,
                    component_version_lookup=component_version_lookup,
                    github_api_lookup=github_api_lookup,
                    invalid_semver_ok=invalid_semver_ok,
                ),
                *ai_assistant.ai_tools.get_vulnerability_tools(
                    db_session=db_session,
                    component_descriptor_lookup=component_descriptor_lookup,
                    component_version_lookup=component_version_lookup,
                    github_api_lookup=github_api_lookup,
                    invalid_semver_ok=invalid_semver_ok,
                )
            ]
        )

        chat_template = [
            ('system', 'You are part of a larger team of agents, each with a specific role in answering a user\'s question. As the "planning_agent", your responsibility is to plan individual tasks for the other agents. These tasks may build upon each other and should ultimately lead to the answer to the user\'s question. Your plan will be handed over to a "execution_agent" who will delegate tasks based on your plan to the following members:'),

            ('system', 'Your task is to be as precise and brief as possible, eliminating unnecessary steps.'),

            ('system', 'Create a step-by-step plan of tasks. Always double-check to ensure all steps are necessary and as precise as possible. Ask yourself if each step is truly necessary.'),

            ('system', 'Take a look at your tools, but dont use them. Only plan! but an agent later can use these tools to implement your plan.'),

            (
                'system',
                'The Delivery Gear is an application that provides various information about OCM Components. Within the application, '
                ' a root component is always selected. The current selected root component is:'
                ' \n<root_component_name>{root_component_name}</root_component_name>'
                ' \n<root_component_version>{root_component_version}</root_component_version>'
                '''
                When calling functions, always keep in mind the following structure of a Component Descriptor:
                    {{\"$id\":\"https://gardener.cloud/schemas/component-descriptor-v2\",\"$schema\":\"https://json-schema.org/draft/2020-12/schema\",\"description\":\"Gardener Component Descriptor v2 schema\",\"definitions\":{{\"meta\":{{\"type\":\"object\",\"description\":\"component descriptor metadata\",\"required\":[\"schemaVersion\"],\"properties\":{{\"schemaVersion\":{{\"type\":\"string\"}}}}}},\"label\":{{\"type\":\"object\",\"required\":[\"name\",\"value\"]}},\"componentName\":{{\"type\":\"string\",\"maxLength\":255,\"pattern\":\"^[a-z0-9.\\\\-]+[.][a-z][a-z]+/[-a-z0-9/_.]*$\"}},\"identityAttributeKey\":{{\"minLength\":2,\"pattern\":\"^[a-z0-9]([-_+a-z0-9]*[a-z0-9])?$\"}},\"relaxedSemver\":{{\"pattern\":\"^[v]?(0|[1-9]\\\\d*)(?:\\\\.(0|[1-9]\\\\d*))?(?:\\\\.(0|[1-9]\\\\d*))?(?:-((?:0|[1-9]\\\\d*|\\\\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\\\\.(?:0|[1-9]\\\\d*|\\\\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\\\\+([0-9a-zA-Z-]+(?:\\\\.[0-9a-zA-Z-]+)*))?$\",\"type\":\"string\"}},\"identityAttribute\":{{\"type\":\"object\",\"propertyNames\":{{\"$ref\":\"#/definitions/identityAttributeKey\"}}}},\"repositoryContext\":{{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{{\"type\":{{\"type\":\"string\"}}}}}},\"ociRepositoryContext\":{{\"allOf\":[{{\"$ref\":\"#/definitions/repositoryContext\"}},{{\"required\":[\"baseUrl\"],\"properties\":{{\"baseUrl\":{{\"type\":\"string\"}},\"type\":{{\"type\":\"string\"}}}}}}]}},\"access\":{{\"type\":\"object\",\"description\":\"base type for accesses (for extensions)\",\"required\":[\"type\"]}},\"githubAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"repoUrl\",\"ref\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"github\"]}},\"repoUrl\":{{\"type\":\"string\"}},\"ref\":{{\"type\":\"string\"}},\"commit\":{{\"type\":\"string\"}}}}}},\"noneAccess\":{{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"None\"]}}}}}},\"sourceDefinition\":{{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/access\"}},{{\"$ref\":\"#/definitions/githubAccess\"}},{{\"$ref\":\"#/definitions/httpAccess\"}}]}}}}}},\"digestSpec\":{{\"type\":\"object\",\"required\":[\"hashAlgorithm\",\"normalisationAlgorithm\",\"value\"],\"properties\":{{\"hashAlgorithm\":{{\"type\":\"string\"}},\"normalisationAlgorithm\":{{\"type\":\"string\"}},\"value\":{{\"type\":\"string\"}}}}}},\"signatureSpec\":{{\"type\":\"object\",\"required\":[\"algorithm\",\"value\",\"mediaType\"],\"properties\":{{\"algorithm\":{{\"type\":\"string\"}},\"value\":{{\"type\":\"string\"}},\"mediaType\":{{\"description\":\"The media type of the signature value\",\"type\":\"string\"}}}}}},\"signature\":{{\"type\":\"object\",\"required\":[\"name\",\"digest\",\"signature\"],\"properties\":{{\"name\":{{\"type\":\"string\"}},\"digest\":{{\"$ref\":\"#/definitions/digestSpec\"}},\"signature\":{{\"$ref\":\"#/definitions/signatureSpec\"}}}}}},\"srcRef\":{{\"type\":\"object\",\"description\":\"a reference to a (component-local) source\",\"properties\":{{\"identitySelector\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}}}}}},\"componentReference\":{{\"type\":\"object\",\"description\":\"a reference to a component\",\"required\":[\"name\",\"componentName\",\"version\"],\"properties\":{{\"componentName\":{{\"$ref\":\"#/definitions/componentName\"}},\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"resourceType\":{{\"type\":\"object\",\"description\":\"base type for resources\",\"required\":[\"name\",\"version\",\"type\",\"relation\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\"}},\"srcRefs\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/srcRef\"}}}},\"relation\":{{\"type\":\"string\",\"enum\":[\"local\",\"external\"]}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/access\"}},{{\"$ref\":\"#/definitions/ociBlobAccess\"}},{{\"$ref\":\"#/definitions/localFilesystemBlobAccess\"}},{{\"$ref\":\"#/definitions/localOciBlobAccess\"}}]}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"ociImageAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"imageReference\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"ociRegistry\"]}},\"imageReference\":{{\"type\":\"string\"}}}}}},\"ociBlobAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"layer\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"ociBlob\"]}},\"ref\":{{\"description\":\"A oci reference to the manifest\",\"type\":\"string\"}},\"mediaType\":{{\"description\":\"The media type of the object this access refers to\",\"type\":\"string\"}},\"digest\":{{\"description\":\"The digest of the targeted content\",\"type\":\"string\"}},\"size\":{{\"description\":\"The size in bytes of the blob\",\"type\":\"number\"}}}}}},\"localFilesystemBlobAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"filename\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"localFilesystemBlob\"]}},\"filename\":{{\"description\":\"filename of the blob that is located in the \\\"blobs\\\" directory\",\"type\":\"string\"}}}}}},\"localOciBlobAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"filename\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"localOciBlob\"]}},\"digest\":{{\"description\":\"digest of the layer within the current component descriptor\",\"type\":\"string\"}}}}}},\"ociImageResource\":{{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\",\"enum\":[\"ociImage\"]}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"$ref\":\"#/definitions/ociImageAccess\"}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"httpAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"url\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"http\"]}},\"url\":{{\"type\":\"string\"}}}}}},\"genericAccess\":{{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"generic\"]}}}}}},\"genericResource\":{{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\",\"enum\":[\"generic\"]}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"$ref\":\"#/definitions/genericAccess\"}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"component\":{{\"type\":\"object\",\"description\":\"a component\",\"required\":[\"name\",\"version\",\"repositoryContexts\",\"provider\",\"sources\",\"componentReferences\",\"resources\"],\"properties\":{{\"name\":{{\"$ref\":\"#/definitions/componentName\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"repositoryContexts\":{{\"type\":\"array\",\"items\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/ociRepositoryContext\"}}]}}}},\"provider\":{{\"type\":\"string\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"sources\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/sourceDefinition\"}}}},\"componentReferences\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/componentReference\"}}}},\"resources\":{{\"type\":\"array\",\"items\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/resourceType\"}},{{\"$ref\":\"#/definitions/ociImageResource\"}},{{\"$ref\":\"#/definitions/genericResource\"}}]}}}}}},\"componentReferences\":{{}}}}}},\"type\":\"object\",\"required\":[\"meta\",\"component\"],\"properties\":{{\"meta\":{{\"$ref\":\"#/definitions/meta\"}},\"component\":{{\"$ref\":\"#/definitions/component\"}},\"signatures\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/signature\"}}}}}}}}
                '''
            ),

            (
                'system',
                'It is always better not to answer a question then answer it the wrong way!'
                ' If you dont know an important thing, express this and dont make something up!'
                ' If the question is not scoped to the current Root Component, please politly answer, that you can only answer questions about the currently selected Root Component.'
            ),
            (
                'human',
                'The new Message says the following:'
                '"{question}"\n'
                'The following messages reoresent the Chat between you and the user up unit now: '
            ),
            (
                'placeholder',
                '{old_chat}'
            ),
        ]

        assistant_prompt = langchain_core.prompts.ChatPromptTemplate.from_messages(chat_template).partial(
            root_component_name=root_component_identity.name,
            root_component_version=root_component_identity.version
        )

        planning_chain = (
            assistant_prompt
            | llm
        )

        self.runnable = planning_chain

    def __call__(
        self,
        state: State
    ) -> State:
        llm_message = self.runnable.invoke({
            'question': state['question'],
            'old_chat': state['old_chat']
        })
        return {
            'current_plan': llm_message.content,
        }


class ExecutionAgent:
    def __init__(
        self,
        root_component_identity: gci.componentmodel.ComponentIdentity,
        component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
        component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
        github_api_lookup,
        db_session: sqlalchemy.orm.session.Session,
        invalid_semver_ok: bool=False,
    ):
        llm =  langchain_openai.AzureChatOpenAI(
            model='gpt-40-128k-1106',
            streaming=True,
        ).bind_tools(
            [
                *ai_assistant.ai_tools.get_ocm_tools(
                    db_session=db_session,
                    component_descriptor_lookup=component_descriptor_lookup,
                    component_version_lookup=component_version_lookup,
                    github_api_lookup=github_api_lookup,
                    invalid_semver_ok=invalid_semver_ok,
                ),
                *ai_assistant.ai_tools.get_license_tools(
                    db_session=db_session,
                    component_descriptor_lookup=component_descriptor_lookup,
                    component_version_lookup=component_version_lookup,
                    github_api_lookup=github_api_lookup,
                    invalid_semver_ok=invalid_semver_ok,
                ),
                *ai_assistant.ai_tools.get_malware_tools(
                    db_session=db_session,
                    component_descriptor_lookup=component_descriptor_lookup,
                    component_version_lookup=component_version_lookup,
                    github_api_lookup=github_api_lookup,
                    invalid_semver_ok=invalid_semver_ok,
                ),
                *ai_assistant.ai_tools.get_vulnerability_tools(
                    db_session=db_session,
                    component_descriptor_lookup=component_descriptor_lookup,
                    component_version_lookup=component_version_lookup,
                    github_api_lookup=github_api_lookup,
                    invalid_semver_ok=invalid_semver_ok,
                )
            ]
        )

        assistant_prompt = langchain_core.prompts.ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are the Plan execuioner who is tasked with executing the following plan:"
                    " {current_plan}"
                    "\n"
                    " This plan was created by the Planning Agent to solve toe following question: {question}"
                    " "
                    " \nWithin the application, there is always a root component selected. Currently the following one is selected:"
                    "   <root_component_name>{root_component_name}</root_component_name>"
                    "   <root_component_version>{root_component_version}</root_component_version>"
                    " "
                    """
                    When calling functions, always keep in mind the following structure of a Component Descriptor:
                        {{\"$id\":\"https://gardener.cloud/schemas/component-descriptor-v2\",\"$schema\":\"https://json-schema.org/draft/2020-12/schema\",\"description\":\"Gardener Component Descriptor v2 schema\",\"definitions\":{{\"meta\":{{\"type\":\"object\",\"description\":\"component descriptor metadata\",\"required\":[\"schemaVersion\"],\"properties\":{{\"schemaVersion\":{{\"type\":\"string\"}}}}}},\"label\":{{\"type\":\"object\",\"required\":[\"name\",\"value\"]}},\"componentName\":{{\"type\":\"string\",\"maxLength\":255,\"pattern\":\"^[a-z0-9.\\\\-]+[.][a-z][a-z]+/[-a-z0-9/_.]*$\"}},\"identityAttributeKey\":{{\"minLength\":2,\"pattern\":\"^[a-z0-9]([-_+a-z0-9]*[a-z0-9])?$\"}},\"relaxedSemver\":{{\"pattern\":\"^[v]?(0|[1-9]\\\\d*)(?:\\\\.(0|[1-9]\\\\d*))?(?:\\\\.(0|[1-9]\\\\d*))?(?:-((?:0|[1-9]\\\\d*|\\\\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\\\\.(?:0|[1-9]\\\\d*|\\\\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\\\\+([0-9a-zA-Z-]+(?:\\\\.[0-9a-zA-Z-]+)*))?$\",\"type\":\"string\"}},\"identityAttribute\":{{\"type\":\"object\",\"propertyNames\":{{\"$ref\":\"#/definitions/identityAttributeKey\"}}}},\"repositoryContext\":{{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{{\"type\":{{\"type\":\"string\"}}}}}},\"ociRepositoryContext\":{{\"allOf\":[{{\"$ref\":\"#/definitions/repositoryContext\"}},{{\"required\":[\"baseUrl\"],\"properties\":{{\"baseUrl\":{{\"type\":\"string\"}},\"type\":{{\"type\":\"string\"}}}}}}]}},\"access\":{{\"type\":\"object\",\"description\":\"base type for accesses (for extensions)\",\"required\":[\"type\"]}},\"githubAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"repoUrl\",\"ref\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"github\"]}},\"repoUrl\":{{\"type\":\"string\"}},\"ref\":{{\"type\":\"string\"}},\"commit\":{{\"type\":\"string\"}}}}}},\"noneAccess\":{{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"None\"]}}}}}},\"sourceDefinition\":{{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/access\"}},{{\"$ref\":\"#/definitions/githubAccess\"}},{{\"$ref\":\"#/definitions/httpAccess\"}}]}}}}}},\"digestSpec\":{{\"type\":\"object\",\"required\":[\"hashAlgorithm\",\"normalisationAlgorithm\",\"value\"],\"properties\":{{\"hashAlgorithm\":{{\"type\":\"string\"}},\"normalisationAlgorithm\":{{\"type\":\"string\"}},\"value\":{{\"type\":\"string\"}}}}}},\"signatureSpec\":{{\"type\":\"object\",\"required\":[\"algorithm\",\"value\",\"mediaType\"],\"properties\":{{\"algorithm\":{{\"type\":\"string\"}},\"value\":{{\"type\":\"string\"}},\"mediaType\":{{\"description\":\"The media type of the signature value\",\"type\":\"string\"}}}}}},\"signature\":{{\"type\":\"object\",\"required\":[\"name\",\"digest\",\"signature\"],\"properties\":{{\"name\":{{\"type\":\"string\"}},\"digest\":{{\"$ref\":\"#/definitions/digestSpec\"}},\"signature\":{{\"$ref\":\"#/definitions/signatureSpec\"}}}}}},\"srcRef\":{{\"type\":\"object\",\"description\":\"a reference to a (component-local) source\",\"properties\":{{\"identitySelector\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}}}}}},\"componentReference\":{{\"type\":\"object\",\"description\":\"a reference to a component\",\"required\":[\"name\",\"componentName\",\"version\"],\"properties\":{{\"componentName\":{{\"$ref\":\"#/definitions/componentName\"}},\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"resourceType\":{{\"type\":\"object\",\"description\":\"base type for resources\",\"required\":[\"name\",\"version\",\"type\",\"relation\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\"}},\"srcRefs\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/srcRef\"}}}},\"relation\":{{\"type\":\"string\",\"enum\":[\"local\",\"external\"]}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/access\"}},{{\"$ref\":\"#/definitions/ociBlobAccess\"}},{{\"$ref\":\"#/definitions/localFilesystemBlobAccess\"}},{{\"$ref\":\"#/definitions/localOciBlobAccess\"}}]}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"ociImageAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"imageReference\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"ociRegistry\"]}},\"imageReference\":{{\"type\":\"string\"}}}}}},\"ociBlobAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"layer\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"ociBlob\"]}},\"ref\":{{\"description\":\"A oci reference to the manifest\",\"type\":\"string\"}},\"mediaType\":{{\"description\":\"The media type of the object this access refers to\",\"type\":\"string\"}},\"digest\":{{\"description\":\"The digest of the targeted content\",\"type\":\"string\"}},\"size\":{{\"description\":\"The size in bytes of the blob\",\"type\":\"number\"}}}}}},\"localFilesystemBlobAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"filename\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"localFilesystemBlob\"]}},\"filename\":{{\"description\":\"filename of the blob that is located in the \\\"blobs\\\" directory\",\"type\":\"string\"}}}}}},\"localOciBlobAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"filename\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"localOciBlob\"]}},\"digest\":{{\"description\":\"digest of the layer within the current component descriptor\",\"type\":\"string\"}}}}}},\"ociImageResource\":{{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\",\"enum\":[\"ociImage\"]}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"$ref\":\"#/definitions/ociImageAccess\"}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"httpAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"url\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"http\"]}},\"url\":{{\"type\":\"string\"}}}}}},\"genericAccess\":{{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"generic\"]}}}}}},\"genericResource\":{{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\",\"enum\":[\"generic\"]}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"$ref\":\"#/definitions/genericAccess\"}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"component\":{{\"type\":\"object\",\"description\":\"a component\",\"required\":[\"name\",\"version\",\"repositoryContexts\",\"provider\",\"sources\",\"componentReferences\",\"resources\"],\"properties\":{{\"name\":{{\"$ref\":\"#/definitions/componentName\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"repositoryContexts\":{{\"type\":\"array\",\"items\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/ociRepositoryContext\"}}]}}}},\"provider\":{{\"type\":\"string\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"sources\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/sourceDefinition\"}}}},\"componentReferences\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/componentReference\"}}}},\"resources\":{{\"type\":\"array\",\"items\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/resourceType\"}},{{\"$ref\":\"#/definitions/ociImageResource\"}},{{\"$ref\":\"#/definitions/genericResource\"}}]}}}}}},\"componentReferences\":{{}}}}}},\"type\":\"object\",\"required\":[\"meta\",\"component\"],\"properties\":{{\"meta\":{{\"$ref\":\"#/definitions/meta\"}},\"component\":{{\"$ref\":\"#/definitions/component\"}},\"signatures\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/signature\"}}}}}}}}
                    """
                ),
                (
                    "system",
                    "It is always better not to answer a question then answer it the wrong way!"
                    " If you dont know an important thing, express this and dont make something up!"
                ),
                (
                    "placeholder",
                    "{messages}"
                ),
                (
                    "human",
                    ' The steps above already have been taken.'
                    ' Answer the question by executing the rest of the plan as good as possible with the healp of your tools.'
                    ' If you have executed the plan create a precise answer for the user.'
                    ' The answer shuld answer the users question fully.'
                    ' Add all important information. Never say something like "Other components also show ..."'
                    ' Dont explain your steps within the anser.'
                    ' # Format:'
                    ' - Answer in valid Markdown'
                    ' - Use Tables if appliable.'
                    ' - At the end, you create a table (witht the following fomrat: \n| Step | Action | Tool Used |\n|------|--------|-----------|\n)'
                    '   which shows the steps you have taken and toolcall you have done.'
                )
            ]
        ).partial(
            root_component_name=root_component_identity.name,
            root_component_version=root_component_identity.version,
        )

        executor_chain = (
            assistant_prompt
            | llm
        )

        self.runnable = executor_chain

    def __call__(self, state: State) -> State:
        llm_message = self.runnable.invoke({
            'current_plan': state["current_plan"],
            'question': state['question'],
            'messages': state['messages'],
        })
        return {
            'messages': [llm_message]
        }


# #####
# Nodes
# #####

def handle_tool_error(state) -> dict:
    error = state.get("error")
    tool_calls = state["messages"][-1].tool_calls
    return {
        "messages":[
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

        if messages := state.get("messages", []):
            output_type = "dict"
            last_message = messages[-1]
        else:
            raise ValueError("No message found in input")

        if not isinstance(last_message, langchain_core.messages.ai.AIMessage):
            raise ValueError("Last message is not an AIMessage")

        def run_one(call:  langchain_core.messages.tool.ToolCall):
            output = self.tools_by_name[call["name"]].invoke(call["args"], config)
            return  langchain_core.messages.tool.ToolMessage(
                content=langgraph.prebuilt.tool_node.str_output(output), name=call["name"], tool_call_id=call["id"]
            )

        with langchain_core.runnables.config.get_executor_for_config(config) as executor:
            outputs = [*executor.map(run_one, last_message.tool_calls)]
            if output_type == "list":
                return outputs
            else:
                return {"messages": outputs}


    async def _afunc(
        self, state: ai_assistant.graph_state.State, config: langchain_core.runnables.RunnableConfig
    ) -> typing.Any:

        if messages := state.get("messages", []):
            output_type = "dict"
            last_message = messages[-1]
        else:
            raise ValueError("No message found in input")

        if not isinstance(last_message, langchain_core.messages.ai.AIMessage):
            raise ValueError("Last message is not an AIMessage")

        async def run_one(call: langchain_core.messages.tool.ToolCall):
            output = await self.tools_by_name[call["name"]].ainvoke(
                call["args"], config
            )
            return langchain_core.messages.tool.ToolMessage(
                content=langgraph.prebuilt.tool_node.str_output(output), name=call["name"], tool_call_id=call["id"]
            )

        outputs = await asyncio.gather(*(run_one(call) for call in last_message.tool_calls))
        if output_type == "list":
            return outputs
        else:
            return {"messages": outputs}


# #####
# Edges
# #####

def tool_router(state: State) -> typing.Literal["tools", "__end__"]:
    """Use in the conditional_edge to route to the ToolNode if the last Message has tool calls, otherwise, routes back to the __end__."""
    if messages := state.get("messages", []):
        last_message = messages[-1]
    else:
        raise ValueError(f"No messages found in input state to tool edge: {state}")

    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        print(f"\n -> tools\n")
        return "tools"

    print("\n -> __end__ \n")
    return "__end__"


# #####
# Graph
# #####

def create_custome_graph(
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
    component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
    github_api_lookup,
    root_component_identity: gci.componentmodel.ComponentIdentity,
    db_session: sqlalchemy.orm.session.Session,
    invalid_semver_ok: bool=False,
):

    builder = langgraph.graph.StateGraph(State)


    builder.add_node(
        'planning_agent',
        PlanningAgent(
            component_descriptor_lookup=component_descriptor_lookup,
            component_version_lookup=component_version_lookup,
            github_api_lookup=github_api_lookup,
            root_component_identity=root_component_identity,
            invalid_semver_ok=invalid_semver_ok,
            db_session=db_session,
        )
    )

    builder.add_node('execution_agent', ExecutionAgent(
        component_descriptor_lookup=component_descriptor_lookup,
        component_version_lookup=component_version_lookup,
        github_api_lookup=github_api_lookup,
        root_component_identity=root_component_identity,
        invalid_semver_ok=invalid_semver_ok,
        db_session=db_session,
    ))

    builder.add_node("tools", create_tool_node_with_fallback(
        [
            *ai_assistant.ai_tools.get_ocm_tools(
                db_session=db_session,
                component_descriptor_lookup=component_descriptor_lookup,
                component_version_lookup=component_version_lookup,
                github_api_lookup=github_api_lookup,
                invalid_semver_ok=invalid_semver_ok,
            ),
            *ai_assistant.ai_tools.get_license_tools(
                db_session=db_session,
                component_descriptor_lookup=component_descriptor_lookup,
                component_version_lookup=component_version_lookup,
                github_api_lookup=github_api_lookup,
                invalid_semver_ok=invalid_semver_ok,
            ),
            *ai_assistant.ai_tools.get_malware_tools(
                db_session=db_session,
                component_descriptor_lookup=component_descriptor_lookup,
                component_version_lookup=component_version_lookup,
                github_api_lookup=github_api_lookup,
                invalid_semver_ok=invalid_semver_ok,
            ),
            *ai_assistant.ai_tools.get_vulnerability_tools(
                db_session=db_session,
                component_descriptor_lookup=component_descriptor_lookup,
                component_version_lookup=component_version_lookup,
                github_api_lookup=github_api_lookup,
                invalid_semver_ok=invalid_semver_ok,
            )
        ]
    ))


    builder.set_entry_point('planning_agent')
    builder.set_finish_point('execution_agent')

    builder.add_edge(
        'planning_agent',
        'execution_agent'
    )

    builder.add_conditional_edges(
        'execution_agent',
        tool_router,
    )

    builder.add_edge(
        'tools',
        'execution_agent',
    )


    #memory = langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string("checkpoints.sqlite")
    memory = langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string(":memory:")


    graph = builder.compile(checkpointer=memory)
    print('==========Graph Created==========')
    print(graph.get_graph().draw_mermaid())
    print('=================================')
    return graph
