import cnudie.retrieve
import langgraph.graph
import langgraph.prebuilt
import ai_assistant.agents.planning_agent
import ai_assistant.agents.ocm_agent
import ai_assistant.agents.supervisor
import ai_assistant.agents.security_agent
import ai_assistant.graph_state
import ai_assistant.utils
import ai_assistant.ai_tools
import langgraph.checkpoint.sqlite
import gci.componentmodel
import ai_assistant.edges
import sqlalchemy.orm.session
import ai_assistant.nodes


def create_custome_graph(
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
    component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
    github_api_lookup,
    root_component_identity: gci.componentmodel.ComponentIdentity,
    db_session: sqlalchemy.orm.session.Session,
    invalid_semver_ok: bool=False,
):

    agent_routing_options=['ocm_agent', 'security_agent', 'summary_agent']

    builder = langgraph.graph.StateGraph(ai_assistant.graph_state.State)

    builder.add_node(
        'planning_agent',
        ai_assistant.agents.planning_agent.PlanningAgent(
            root_component_identity=root_component_identity,
            members=agent_routing_options
        )
    )

    builder.add_node("supervisor_agent", ai_assistant.agents.supervisor.SupervisorAgent(
        root_component_identity=root_component_identity,
        members=agent_routing_options
    ))

    builder.add_node("ocm_agent", ai_assistant.agents.ocm_agent.OcmAgent(
        component_descriptor_lookup=component_descriptor_lookup,
        component_version_lookup=component_version_lookup,
        github_api_lookup=github_api_lookup,
        root_component_identity=root_component_identity,
        invalid_semver_ok=invalid_semver_ok,
    ))

    builder.add_node("security_agent", ai_assistant.agents.security_agent.SecurityAgent(
        component_descriptor_lookup=component_descriptor_lookup,
        component_version_lookup=component_version_lookup,
        github_api_lookup=github_api_lookup,
        root_component_identity=root_component_identity,
        invalid_semver_ok=invalid_semver_ok,
        db_session=db_session
    ))

    builder.add_node("routing_tool", ai_assistant.utils.create_tool_node_with_fallback(
        ai_assistant.ai_tools.create_routing_tools_list(
            routing_options=agent_routing_options,
        )
    ))
    builder.add_node("tools", ai_assistant.utils.create_tool_node_with_fallback(
        [
            *ai_assistant.ai_tools.get_ocm_tools(
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

    builder.add_node('agent_cleanup', ai_assistant.nodes.AgentCleanup())

    builder.add_node('summary_agent', ai_assistant.nodes.SummaryAgent())

    builder.set_entry_point('planning_agent')

    builder.add_edge('planning_agent', 'supervisor_agent')

    # Route from supervisor_agent to member_agents
    builder.add_conditional_edges('supervisor_agent', ai_assistant.edges.create_edge_conditional_routing(members=agent_routing_options))

    # route to tool node if tool call else to supervisor_agent
    builder.add_conditional_edges(
        'ocm_agent',
        ai_assistant.edges.tool_router,
    )
    builder.add_conditional_edges(
        'security_agent',
        ai_assistant.edges.tool_router,
    )
    builder.add_conditional_edges(
        'tools',
        ai_assistant.edges.tool_back_to_agent,
    )

    builder.add_edge(
        'agent_cleanup',
        'supervisor_agent',
    )

    builder.add_edge('summary_agent', langgraph.graph.END)


    #memory = langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string("checkpoints.sqlite")
    memory = langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string(":memory:")


    graph = builder.compile(checkpointer=memory)
    print('==========Graph Created==========')
    print(graph.get_graph().draw_mermaid())
    print('=================================')
    return graph
