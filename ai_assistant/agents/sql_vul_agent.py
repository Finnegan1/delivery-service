import ai_assistant.graph_state
import langchain
import langchain_openai
import langchain_core.prompts
import langchain.agents
import langchain.agents.agent_types
import langchain.agents.agent_toolkits
import langchain_community.agent_toolkits
import langchain_core.messages
import langchain_community.utilities
import sqlalchemy

class SqlVulAgent:
    def __init__(self):
        llm =  langchain_openai.AzureChatOpenAI(
            model='gpt-40-32k-0613'
        )

        prompt_template = langchain_core.prompts.ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    'You are an agent designed to interact with a SQL database.'
                    'Given an input question, create a syntactically correct {dialect} query to run, then look at the results of the query and return the answer.'
                    'Unless the user specifies a specific number of examples they wish to obtain, always limit your query to at most {top_k} results.'
                    'You can order the results by a relevant column to return the most interesting examples in the database.'
                    'Never query for all the columns from a specific table, only ask for the relevant columns given the question.'
                    'You have access to tools for interacting with the database.'
                    'Only use the given tools. Only use the information returned by the tools to construct your final answer.'
                    'You MUST double check your query before executing it. If you get an error while executing a query, rewrite the query and try again.'
                    ''
                    'DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.'
                    ''
                    'The DB is named delivery_db. This is a Postgres Database which has one relation. The public.artefact_metadata relation. This realtion in used to store several information about the delivery gear.'
                    'The realtion is ot fully normatlized. Dependeing on the type, the data column has a different json structure. Here are the types and the according sql structure:'
                    '''

                    ### Type:
                    - cloud.gardener/compliance/landscape/endpoints
                    ### General information:
                    - This type contains information about various endpoints, including their ports, URL, and metadata such as the name, cluster kind, and endpoint kind.
                    - Some notes about the json:
                        - `"ports"` is an array of integers which represent the network ports associated with the endpoint.
                        - `"endpoint"` is a string that represents the URI of the endpoint.
                        - `"metadata"` is an object containing additional information about the endpoint:
                        - `"name"` is a string representing the name of the endpoint, but it can be `null`.
                        - `"cluster_kind"` is a string representing the kind of the cluster.
                        - `"cluster_name"` is a string representing the name of the cluster, but it can be `null`.
                        - `"endpoint_kind"` is a string representing the kind of the endpoint.

                    ### Type:
                    - codechecks/aggregated
                    ### General infomration:
                    - This type contains information about code checks, including the levels of findings (low, high, info, medium) and a report URL.
                    - Some notes about the json:
                        - `findings` is an object that holds information about the findings. Each key in this object represents a different severity level and the value is the count of findings for each severity.
                        - `detailed_report_link` is a URL where the detailed report can be found.
                        - `risk_score` is the overall risk score of the findings.
                        - `summary_report_link` is a URL where a summary report can be found.
                        - `risk_severity_level` represents the severity level of the risk.

                    ### Type:
                    - compliance/snapshots
                    ### General infomration:
                    - This type contains details about the compliance snapshots including the status, service, timestamp, and other related information.
                    - Some notes about the json:
                        - `status_value` could be a string or a number or null indicating the status of a service.
                        - `service_value` could be a string or null indicating the service name.
                        - `timestamp_value` is a string indicating the timestamp when the status was recorded.
                        - `config_name_value` is a string indicating the name of the configuration.
                        - `correlation_id_value` is a string serving as a unique identifier for the correlation.
                        - `latest_processing_date_value` is a string indicating the latest date when the processing happened.

                    ### Type:
                    - finding/vulnerability
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
                    - malware
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
                    - meta/artefact_scan_info
                    ### General information:
                    - This type contains a report URL for an artefact scan.

                    ### Type:
                    - os_ids
                    ### General information:
                    - This type contains information about the operating system, including its ID, name, variant, and version.

                    ### Type:
                    - rescorings
                    ### General information
                    - This type contains information about the reassessment of the severity of a vulnerability, including the user who made the reassessment, the reassessment comment, the vulnerability details, and the new severity rating.

                    ### Type:
                    - structure_info
                    ### General information
                    - This type contains information about a software package, including its name, version, identified licenses, a report URL, and information about its location in the filesystem.

                    '''
                ),
                (
                    "human",
                    "Answer the following questions as best you can. You have access to the following tools:"
                    "{tools}"
                    "Begin!"
                    "Thought:{agent_scratchpad}"
                ),
                ("placeholder", "{messages}"),
            ]
        )

        pg_uri = f"postgresql+psycopg2://postgres:MyPassword@localhost:5431/delivery-db"
        engine = sqlalchemy.create_engine(
            url=pg_uri
        )
        db = langchain_community.utilities.SQLDatabase(engine)
        toolkit = langchain.agents.agent_toolkits.SQLDatabaseToolkit(db=db, llm=llm)

        self.runnable = langchain_community.agent_toolkits.create_sql_agent(
            llm=llm,
            toolkit=toolkit,
            verbose=True,
            agent_type=langchain.agents.agent_types.AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            prompt=prompt_template,
        )

    def __call__(self, state: ai_assistant.graph_state.State):
        state_messages: list[langchain_core.messages.MessageLikeRepresentation] = state['messages']
        llm_message = self.runnable.invoke({'messages': state_messages})
        return {'messages': [llm_message]}
