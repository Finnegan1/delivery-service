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

class FindingsAgent:
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
                    "You are a helpful expert helping with all findings in regard to OCM (Open Compoennt Model) Components."
                    " Findings are results from Scanne, which are done within the delivery Gear."
                    " The Delivery Gear is an application, which healps to get an overview about OCM components as well as scann these for vulnerbilities, malware and licenses."
                    " Use the provided tools to get information about an specific OCM Component, the Dependency tree of an OCM Componentscann ot results for vulnerbilities, malware and licenses scanns."
                    '''

                    # The following are the descriptions for the types of finding:

                    ### Type:
                    - CODECHECKS_AGGREGATED
                    ### General infomration:
                    - This type contains information about code checks, including the levels of findings (low, high, info, medium) and a report URL.
                    - Some notes about the json:
                        - `findings` is an object that holds information about the findings. Each key in this object represents a different severity level and the value is the count of findings for each severity.
                        - `detailed_report_link` is a URL where the detailed report can be found.
                        - `risk_score` is the overall risk score of the findings.
                        - `summary_report_link` is a URL where a summary report can be found.
                        - `risk_severity_level` represents the severity level of the risk.

                    ### Type:
                    - VULNERABILITY
                    ### General information:
                    - This type contains information about detected vulnerabilities, including a CVE identifier, CVSS details, severity level, and a report URL.
                    ### JSON Schema in data Column:
                    - {{
                        "cve": "<CVE Identifier>",
                        "cvss": {{
                        "scope": "<Scope of Impact>",
                        "integrity": "<Impact on Integrity>",
                        "availability": "<Impact on Availability>",
                        "access_vector": "<Access Vector>",
                        "confidentiality": "<Impact on Confidentiality>",
                        "user_interaction": "<User Interaction Requirement>",
                        "attack_complexity": "<Attack Complexity>",
                        "privileges_required": "<Privileges Required>"
                        }},
                        "summary": "<Summary of the Vulnerability>",
                        "base_url": "<Base URL of the Vulnerability Database>",
                        "group_id": <Group ID>,
                        "severity": "<Severity of the Vulnerability>",
                        "product_id": <Product ID>,
                        "report_url": "<URL of the Vulnerability Report>",
                        "package_name": "<Name of the Affected Package>",
                        "cvss_v3_score": <CVSS v3 Score>,
                        "package_version": "<Version of the Affected Package>"
                    }}

                    ### Type:
                    - MALWARE
                    ### General information:
                    - This type contains information about any detected malware. In this case, it is empty, indicating no malware was found.
                    - Some notes about the fields:
                        - `findings`: An array that contains findings from a scan. It can be empty if no findings are found.
                        - `meta`: Metadata about the scan. This field may be optional as it is not present in all your examples.
                            - `scanned_octets`: The number of octets that were scanned.
                            - `scan_duration_seconds`: The duration of the scan in seconds.
                            - `scanned_content_digest`: A SHA256 digest of the scanned content.
                            - `receive_duration_seconds`: The duration of receiving the content in seconds.
                        - `name`: The name of the scanned item.
                        - `status`: The status of the scan.
                        - `details`: Details about the scan or found issues. This field may be optional as it is not present in all your examples.
                        - `malware_status`: The status of malware found. This field may be optional as it is not present in all your examples.
                        - `metadata`: Metadata about the scan.
                        - `signature_version`: The signature version used for the scan.
                        - `clamav_version_str`: The version of ClamAV used for the scan.
                        - `virus_definition_timestamp`: The timestamp when the virus definitions were last updated, in ISO 8601 format.
                        - `severity`: The severity of the findings. This field may be optional as it is not present in all your examples.

                    ### Type:
                    - ARTEFACT_SCAN_INFO
                    ### General information:
                    - This type contains a report URL for an artefact scan.

                    ### Type:
                    - OS_IDS
                    ### General information:
                    - This type contains information about the operating system, including its ID, name, variant, and version.

                    '''
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
            root_component_version=root_component_identity.version
        )

        tools = ai_tools.create_vulnerability_tools_list(
            db_session=db_session,
            component_descriptor_lookup=component_descriptor_lookup,
            component_version_lookup=component_version_lookup,
            github_api_lookup=github_api_lookup,
            invalid_semver_ok=invalid_semver_ok,
        )

        self.runnable = assistant_prompt | llm.bind_tools(tools)

    def __call__(self, state: ai_assistant.graph_state.State) -> ai_assistant.graph_state.State:
        llm_message = self.runnable.invoke({
            'agent_task': state['agent_task'],
            'agent_messages': state['agent_messages'],
        })
        return {
            'agent_messages': state['agent_messages'] + [llm_message],
            'next_agent': 'findings_agent',
            'agent_task': state['agent_task'],
            'answer': state['answer'],
            'current_plan': state['current_plan'],
            'question': state['question'],
            'executed_tasks_results': state['executed_tasks_results'],
        }
