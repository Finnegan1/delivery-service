import gci.componentmodel
import langchain_core.runnables
import langchain_core.prompts
import ai_assistant.ai_tools
import ai_assistant.graph_state
import langchain_core.messages
import langchain_openai
import cnudie.retrieve
import ai_assistant.ai_assistant

class OcmAgent:
    def __init__(
        self,
        component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
        component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
        github_api_lookup,
        root_component_identity: gci.componentmodel.ComponentIdentity,
        invalid_semver_ok: bool=False,
    ) -> None:
        llm =  langchain_openai.AzureChatOpenAI(
            model='gpt-40-128k-1106'
        )
        assistant_prompt = langchain_core.prompts.ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful expert on OCM (Open Compoennt Model)."
                    " Users of the Deliver Gear can chat with you."
                    " The Delivery Gear is an application, which healps to get an overview about OCM components as well as scann these for vulnerbilities, malware and licenses."
                    " Use the provided tools to get information about an specific OCM Component, the Dependency tree of an OCM Componentscann ot results for vulnerbilities, malware and licenses scanns."
                    " When searching, be persistent. Expand your query bounds if the first search returns no results. "
                    " If a search comes up empty, expand your search before giving up."
                    " \nWithin the application, there is always a root component selected. Currently the following one is selected:"
                    "   <root_component_name>{root_component_name}</root_component_name>"
                    "   <root_component_version>{root_component_version}</root_component_version>"
                    ""
                    """
                    When calling functions, always keep in mind the following structure of a Component Descriptor:
                        {{\"$id\":\"https://gardener.cloud/schemas/component-descriptor-v2\",\"$schema\":\"https://json-schema.org/draft/2020-12/schema\",\"description\":\"Gardener Component Descriptor v2 schema\",\"definitions\":{{\"meta\":{{\"type\":\"object\",\"description\":\"component descriptor metadata\",\"required\":[\"schemaVersion\"],\"properties\":{{\"schemaVersion\":{{\"type\":\"string\"}}}}}},\"label\":{{\"type\":\"object\",\"required\":[\"name\",\"value\"]}},\"componentName\":{{\"type\":\"string\",\"maxLength\":255,\"pattern\":\"^[a-z0-9.\\\\-]+[.][a-z][a-z]+/[-a-z0-9/_.]*$\"}},\"identityAttributeKey\":{{\"minLength\":2,\"pattern\":\"^[a-z0-9]([-_+a-z0-9]*[a-z0-9])?$\"}},\"relaxedSemver\":{{\"pattern\":\"^[v]?(0|[1-9]\\\\d*)(?:\\\\.(0|[1-9]\\\\d*))?(?:\\\\.(0|[1-9]\\\\d*))?(?:-((?:0|[1-9]\\\\d*|\\\\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\\\\.(?:0|[1-9]\\\\d*|\\\\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\\\\+([0-9a-zA-Z-]+(?:\\\\.[0-9a-zA-Z-]+)*))?$\",\"type\":\"string\"}},\"identityAttribute\":{{\"type\":\"object\",\"propertyNames\":{{\"$ref\":\"#/definitions/identityAttributeKey\"}}}},\"repositoryContext\":{{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{{\"type\":{{\"type\":\"string\"}}}}}},\"ociRepositoryContext\":{{\"allOf\":[{{\"$ref\":\"#/definitions/repositoryContext\"}},{{\"required\":[\"baseUrl\"],\"properties\":{{\"baseUrl\":{{\"type\":\"string\"}},\"type\":{{\"type\":\"string\"}}}}}}]}},\"access\":{{\"type\":\"object\",\"description\":\"base type for accesses (for extensions)\",\"required\":[\"type\"]}},\"githubAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"repoUrl\",\"ref\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"github\"]}},\"repoUrl\":{{\"type\":\"string\"}},\"ref\":{{\"type\":\"string\"}},\"commit\":{{\"type\":\"string\"}}}}}},\"noneAccess\":{{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"None\"]}}}}}},\"sourceDefinition\":{{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/access\"}},{{\"$ref\":\"#/definitions/githubAccess\"}},{{\"$ref\":\"#/definitions/httpAccess\"}}]}}}}}},\"digestSpec\":{{\"type\":\"object\",\"required\":[\"hashAlgorithm\",\"normalisationAlgorithm\",\"value\"],\"properties\":{{\"hashAlgorithm\":{{\"type\":\"string\"}},\"normalisationAlgorithm\":{{\"type\":\"string\"}},\"value\":{{\"type\":\"string\"}}}}}},\"signatureSpec\":{{\"type\":\"object\",\"required\":[\"algorithm\",\"value\",\"mediaType\"],\"properties\":{{\"algorithm\":{{\"type\":\"string\"}},\"value\":{{\"type\":\"string\"}},\"mediaType\":{{\"description\":\"The media type of the signature value\",\"type\":\"string\"}}}}}},\"signature\":{{\"type\":\"object\",\"required\":[\"name\",\"digest\",\"signature\"],\"properties\":{{\"name\":{{\"type\":\"string\"}},\"digest\":{{\"$ref\":\"#/definitions/digestSpec\"}},\"signature\":{{\"$ref\":\"#/definitions/signatureSpec\"}}}}}},\"srcRef\":{{\"type\":\"object\",\"description\":\"a reference to a (component-local) source\",\"properties\":{{\"identitySelector\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}}}}}},\"componentReference\":{{\"type\":\"object\",\"description\":\"a reference to a component\",\"required\":[\"name\",\"componentName\",\"version\"],\"properties\":{{\"componentName\":{{\"$ref\":\"#/definitions/componentName\"}},\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"resourceType\":{{\"type\":\"object\",\"description\":\"base type for resources\",\"required\":[\"name\",\"version\",\"type\",\"relation\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\"}},\"srcRefs\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/srcRef\"}}}},\"relation\":{{\"type\":\"string\",\"enum\":[\"local\",\"external\"]}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/access\"}},{{\"$ref\":\"#/definitions/ociBlobAccess\"}},{{\"$ref\":\"#/definitions/localFilesystemBlobAccess\"}},{{\"$ref\":\"#/definitions/localOciBlobAccess\"}}]}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"ociImageAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"imageReference\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"ociRegistry\"]}},\"imageReference\":{{\"type\":\"string\"}}}}}},\"ociBlobAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"layer\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"ociBlob\"]}},\"ref\":{{\"description\":\"A oci reference to the manifest\",\"type\":\"string\"}},\"mediaType\":{{\"description\":\"The media type of the object this access refers to\",\"type\":\"string\"}},\"digest\":{{\"description\":\"The digest of the targeted content\",\"type\":\"string\"}},\"size\":{{\"description\":\"The size in bytes of the blob\",\"type\":\"number\"}}}}}},\"localFilesystemBlobAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"filename\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"localFilesystemBlob\"]}},\"filename\":{{\"description\":\"filename of the blob that is located in the \\\"blobs\\\" directory\",\"type\":\"string\"}}}}}},\"localOciBlobAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"filename\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"localOciBlob\"]}},\"digest\":{{\"description\":\"digest of the layer within the current component descriptor\",\"type\":\"string\"}}}}}},\"ociImageResource\":{{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\",\"enum\":[\"ociImage\"]}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"$ref\":\"#/definitions/ociImageAccess\"}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"httpAccess\":{{\"type\":\"object\",\"required\":[\"type\",\"url\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"http\"]}},\"url\":{{\"type\":\"string\"}}}}}},\"genericAccess\":{{\"type\":\"object\",\"required\":[\"type\"],\"properties\":{{\"type\":{{\"type\":\"string\",\"enum\":[\"generic\"]}}}}}},\"genericResource\":{{\"type\":\"object\",\"required\":[\"name\",\"version\",\"type\",\"access\"],\"properties\":{{\"name\":{{\"type\":\"string\",\"$ref\":\"#/definitions/identityAttributeKey\"}},\"extraIdentity\":{{\"$ref\":\"#/definitions/identityAttribute\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"type\":{{\"type\":\"string\",\"enum\":[\"generic\"]}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"access\":{{\"$ref\":\"#/definitions/genericAccess\"}},\"digest\":{{\"oneOf\":[{{\"type\":\"null\"}},{{\"$ref\":\"#/definitions/digestSpec\"}}]}}}}}},\"component\":{{\"type\":\"object\",\"description\":\"a component\",\"required\":[\"name\",\"version\",\"repositoryContexts\",\"provider\",\"sources\",\"componentReferences\",\"resources\"],\"properties\":{{\"name\":{{\"$ref\":\"#/definitions/componentName\"}},\"version\":{{\"$ref\":\"#/definitions/relaxedSemver\"}},\"repositoryContexts\":{{\"type\":\"array\",\"items\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/ociRepositoryContext\"}}]}}}},\"provider\":{{\"type\":\"string\"}},\"labels\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/label\"}}}},\"sources\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/sourceDefinition\"}}}},\"componentReferences\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/componentReference\"}}}},\"resources\":{{\"type\":\"array\",\"items\":{{\"anyOf\":[{{\"$ref\":\"#/definitions/resourceType\"}},{{\"$ref\":\"#/definitions/ociImageResource\"}},{{\"$ref\":\"#/definitions/genericResource\"}}]}}}}}},\"componentReferences\":{{}}}}}},\"type\":\"object\",\"required\":[\"meta\",\"component\"],\"properties\":{{\"meta\":{{\"$ref\":\"#/definitions/meta\"}},\"component\":{{\"$ref\":\"#/definitions/component\"}},\"signatures\":{{\"type\":\"array\",\"items\":{{\"$ref\":\"#/definitions/signature\"}}}}}}}}
                    """

                ),
                (
                    "human",
                    " Your task is: {agent_task}"
                    " Tyr to solve this task with the tooly at your hand."
                ),
                ("placeholder", "{agent_messages}"),
            ]
        ).partial(
            root_component_name=root_component_identity.name,
            root_component_version=root_component_identity.version
        )

        tools = ai_assistant.ai_tools.get_ocm_tools(
            component_descriptor_lookup=component_descriptor_lookup,
            component_version_lookup=component_version_lookup,
            github_api_lookup=github_api_lookup,
            invalid_semver_ok=invalid_semver_ok,
        )

        self.runnable = assistant_prompt | llm.bind_tools(tools)

    def __call__(self, state: ai_assistant.graph_state.State) -> ai_assistant.graph_state.State:
        agent_messages: list[langchain_core.messages.MessageLikeRepresentation] = state.get('agent_messages', [])
        llm_message = self.runnable.invoke({'agent_messages': agent_messages, 'agent_task': state['agent_task']})
        return {
            'next_agent': 'ocm_agent',
            'agent_task': state['agent_task'],
            'agent_messages': agent_messages + [llm_message],
            'executed_tasks_results': state.get('executed_tasks_results', {}),
            'current_plan': state['current_plan'],
            'question': state['question'],
            'answer': state['answer'],
        }
