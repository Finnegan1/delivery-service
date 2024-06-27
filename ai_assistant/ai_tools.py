import math
import pprint
import re
import typing

import cnudie.retrieve
import cnudie.util
import dso.model
import gci.componentmodel
import langchain.tools
import langchain_core
import langchain_core.pydantic_v1
import sqlalchemy
import sqlalchemy.orm.query
import sqlalchemy.orm.session

import components
import deliverydb.model
import deliverydb.util
import features

def _get_component(
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
    component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
    component_name: str,
    component_version: str,
    invalid_semver_ok: bool = False,
):
    if component_version == 'greatest':
        component_version = components.greatest_version_if_none(
            component_name=component_name,
            version=None,
            version_lookup=component_version_lookup,
            version_filter=features.VersionFilter.RELEASES_ONLY,
            invalid_semver_ok=invalid_semver_ok,
        )

    return component_descriptor_lookup(
        gci.componentmodel.ComponentIdentity(component_name, component_version),
        None,
    )



def get_ocm_tools(
    db_session: sqlalchemy.orm.session.Session,
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
    component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
    github_api_lookup,
    invalid_semver_ok: bool=False,
) -> list[langchain.tools.BaseTool]:

    class GetComponentDescriptorInformationSchema(langchain_core.pydantic_v1.BaseModel):
        component_name: str = langchain_core.pydantic_v1.Field(
            description=(
                'The name of the OCM Component for which the Component Information should'
                ' be acquired.'
            )
        )
        component_version:str = langchain_core.pydantic_v1.Field(
            description=(
                'Version of the OCM Component. It should be a string following the semantic'
                ' versioning format (e.g., "2.1.1") or the string "greatest".'
            )
        )
        information: list[typing.Literal[
            'componentName',
            'componentVersion',
            'sources',
            'componentReferences_names',
            'componentReferences_identifications',
            'os'
        ]] = langchain_core.pydantic_v1.Field(
            description='Which information about the component will be returned.',
        )

    class GetComponentDescriptorInformation(langchain.tools.BaseTool):
        name = 'get_component_descriptor_information'
        description = (
            'A tool that Retrieves information about an OCM Component based on a component name'
            ' and version.'
        )
        args_schema: typing.Type[
            langchain_core.pydantic_v1.BaseModel
        ] | None = GetComponentDescriptorInformationSchema

        def _run(
            self,
            component_name: str,
            component_version:str,
            information: list[typing.Literal[
                'componentName',
                'componentVersion',
                'sources',
                'componentReferences_names',
                'componentReferences_identifications'
            ]]
        ):
            if component_version == 'greatest':
                component_version = components.greatest_version_if_none(
                    component_name=component_name,
                    version=None,
                    version_lookup=component_version_lookup,
                    version_filter=features.VersionFilter.RELEASES_ONLY,
                    invalid_semver_ok=invalid_semver_ok,
                )

            try:
                component_descriptor = _get_component(
                    component_name=component_name,
                    component_version=component_version,
                    component_descriptor_lookup=component_descriptor_lookup,
                    component_version_lookup=component_version_lookup,
                )
            except Exception as e:
                return f'''
                    Querying the Component Descriptor with the following Name and
                    Version was not possible.

                    Name: {component_name}
                    Version: {component_version}

                    Thrown Exception:
                        {e}
                '''

            result_map = {}

            if 'componentName' in information:
                result_map['componentName'] = component_descriptor.component.name
            if 'componentVersion' in information:
                result_map['componentVersion'] = component_descriptor.component.version
            if 'sources' in information:
                result_map['sources'] = component_descriptor.component.sources
            if 'componentReferences_names' in information:
                result_map['componentReferences_names'] = [
                    reference.componentName
                    for reference
                    in component_descriptor.component.componentReferences
                ]
            if 'componentReferences_identifications' in information:
                result_map['componentReferences_identifications'] = [
                    f'{reference.componentName}:{reference.version}'
                    for reference
                    in component_descriptor.component.componentReferences
                ]
            if 'os' in information:
                os_query = db_session.query(
                    deliverydb.model.ArtefactMetaData.data.op('->>')('os_info'),
                ).filter(
                    deliverydb.model.ArtefactMetaData.type == dso.model.Datatype.OS_IDS,
                    sqlalchemy.or_(deliverydb.util.ArtefactMetadataQueries.component_queries(
                        components=[gci.componentmodel.ComponentIdentity(
                            name=component_name,
                            version=component_version,
                        )],
                    )),
                )
                result_map['os'] = os_query.first()

            return result_map

    class SearchInTransitiveComponentReferencesByNamesSchema(langchain_core.pydantic_v1.BaseModel):
        root_component_name: str = langchain_core.pydantic_v1.Field(
            description='Name of the root component that serves as the starting point for the tree.'
        )
        root_component_version: str = langchain_core.pydantic_v1.Field(
            description=(
                'Version of the root component that serves as the starting point for the tree.'
            ),
        )
        searched_component_names: list[str] = langchain_core.pydantic_v1.Field(
            description=(
                'Component names to be searched for in the component reference tree structure.'
            ),
        )

    class SearchInTransitiveComponentReferencesByNames(langchain.tools.BaseTool):
        name = 'search_in_transitive_component_references_by_names'
        description = (
            'A tool that uses names to search for a components within a component reference tree.'
        )
        args_schema: typing.Type[
            langchain_core.pydantic_v1.BaseModel
        ] | None = SearchInTransitiveComponentReferencesByNamesSchema

        def _run(
            self,
            root_component_name: str,
            root_component_version: str,
            searched_component_names: list[str],
        ):
            if len(searched_component_names) == 0:
                return 'You need to provide at least one valid name in searched_component_names!'

            if root_component_version == 'greatest':
                root_component_version = components.greatest_version_if_none(
                    component_name=root_component_name,
                    version=None,
                    version_lookup=component_version_lookup,
                    version_filter=features.VersionFilter.RELEASES_ONLY,
                    invalid_semver_ok=invalid_semver_ok,
                )

            component_references = components.resolve_component_dependencies(
                component_name=root_component_name,
                component_version=root_component_version,
                component_descriptor_lookup=component_descriptor_lookup,
                ctx_repo=None,
            )

            filtered_component_references = [
                {
                    'name': component.component.name,
                    'version': component.component.version,
                }
                for component
                in component_references
                if component.component.name in searched_component_names
            ]
            return {'componentReferences': filtered_component_references}


    class SearchInTransitiveComponentReferencesByOSSchema(langchain_core.pydantic_v1.BaseModel):
        root_component_name: str = langchain_core.pydantic_v1.Field(
            description='Name of the root component that serves as the starting point for the tree.'
        )
        root_component_version: str = langchain_core.pydantic_v1.Field(
            description=(
                'Version of the root component that serves as the starting point for the tree.'
            ),
        )
        searched_component_os: list[str] = langchain_core.pydantic_v1.Field(
            description=(
                'List of Operating Systems to be searched for in the transitive component'
                ' references tree.'
                ' Must be written in lower case! Example input is: ["debian", "alpine"]'
            ),
        )

    class SearchInTransitiveComponentReferencesByOS(langchain.tools.BaseTool):
        name='search_in_transitive_component_references_by_os'
        description=(
            'Searches for components by the os, they are based on. The search takes place in the'
            ' transitive references of a component.'
        )
        args_schema: typing.Type[
            langchain_core.pydantic_v1.BaseModel
        ] | None = SearchInTransitiveComponentReferencesByOSSchema

        def _run(
            self,
            root_component_name: str,
            root_component_version: str,
            searched_component_os: list[str],
        ):
            if len(searched_component_os) == 0:
                return 'You need to provide at least one valid os name in searched_component_os!'

            if root_component_version == 'greatest':
                root_component_version = components.greatest_version_if_none(
                    component_name=root_component_name,
                    version=None,
                    version_lookup=component_version_lookup,
                    version_filter=features.VersionFilter.RELEASES_ONLY,
                    invalid_semver_ok=invalid_semver_ok,
                )

            component_references = components.resolve_component_dependencies(
                component_name=root_component_name,
                component_version=root_component_version,
                component_descriptor_lookup=component_descriptor_lookup,
                ctx_repo=None,
            )

            reference_ids = [
                gci.componentmodel.ComponentIdentity(
                    name=reference.component.name,
                    version=reference.component.version,
                )
                for reference
                in component_references
            ]

            findings_query = db_session.query(
                deliverydb.model.ArtefactMetaData.component_name,
                deliverydb.model.ArtefactMetaData.component_version,
                deliverydb.model.ArtefactMetaData.data['os_info'].op('->>')('ID'),
            ).filter(
                sqlalchemy.or_(deliverydb.util.ArtefactMetadataQueries.component_queries(
                    components=reference_ids
                )),
                deliverydb.model.ArtefactMetaData.type == dso.model.Datatype.OS_IDS,
                deliverydb.model.ArtefactMetaData.data['os_info']
                .op('->>')('ID')
                .in_(searched_component_os)
            ).distinct()

            findings = findings_query.all()

            return findings


    return [
        GetComponentDescriptorInformation(),
        SearchInTransitiveComponentReferencesByNames(),
        SearchInTransitiveComponentReferencesByOS(),
    ]


def create_routing_tools_list(routing_options: list[str]) -> list[langchain.tools.BaseTool]:

    class RouteToolSchema(langchain_core.pydantic_v1.BaseModel):
        next: str = langchain_core.pydantic_v1.Field(
            description="Next Node",
            anyOf=[{"enum": routing_options}]
        )

    class RouteTool(langchain.tools.BaseTool):
        name = "route"
        description = "A tool to route requests based on the next step"
        args_schema: typing.Type[langchain_core.pydantic_v1.BaseModel] | None = RouteToolSchema

        def _run(self, next: str):
            print(f'Next Agent: {next}')
            return next

    return [RouteTool()]


def get_vulnerability_tools(
    db_session: sqlalchemy.orm.session.Session,
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
    component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
    github_api_lookup,
    invalid_semver_ok: bool=False,
) -> list[langchain.tools.BaseTool]:

    class GetVulnerabilityFindingsForComponentsSchema(langchain_core.pydantic_v1.BaseModel):
        component_identities: list[str] = langchain_core.pydantic_v1.Field(
            description='''
                Component Identities: A component identity is always a concatenation of a
                'Component Name,' ':' and 'Component Version.'
            '''
        )

    class GetVulnerabilityFindingsForComponents(langchain.tools.BaseTool):
        name = 'get_vulnerability_findings_for_component'
        description = (
            'A tool that returns the findings of a specific type or types for specific component'
        )
        args_schema: typing.Type[
            langchain_core.pydantic_v1.BaseModel
        ] | None = GetVulnerabilityFindingsForComponentsSchema

        def _run(
            self,
            component_identities: list[str]
        ):
            component_ids = [
                gci.componentmodel.ComponentIdentity(
                    name=component_identitie.split(':')[0],
                    version=component_identitie.split(':')[1],
                )
                if component_identitie.split(':')[1] != 'greatest'
                else gci.componentmodel.ComponentIdentity(
                    name=component_identitie.split(':')[0],
                    version=components.greatest_version_if_none(
                        component_name=component_identitie.split(':')[0],
                        version=None,
                        version_lookup=component_version_lookup,
                        version_filter=features.VersionFilter.RELEASES_ONLY,
                        invalid_semver_ok=invalid_semver_ok,
                    )
                )
                for component_identitie
                in component_identities
            ]

            findings_query = db_session.query(deliverydb.model.ArtefactMetaData).filter(
                sqlalchemy.or_(deliverydb.util.ArtefactMetadataQueries.component_queries(
                    components=component_ids
                )),
                deliverydb.model.ArtefactMetaData.type.__eq__(dso.model.Datatype.VULNERABILITY),
            )

            findings_raw = findings_query.all()
            findings = [
                deliverydb.util.db_artefact_metadata_to_dso(raw)
                for raw in findings_raw
            ]

            pprint.pprint([{
                f'{finding.artefact.component_name}:{finding.artefact.component_version}': finding.data
            } for finding in findings])

            return [{
                f'{finding.artefact.component_name}:{finding.artefact.component_version}': finding.data
            } for finding in findings]

    class GetTransitiveReferencesWithVulnerabilitySchema(langchain_core.pydantic_v1.BaseModel):
        root_component_name: str = langchain_core.pydantic_v1.Field(
            description=(
                'Name of the component which serves as root for the component references Tree.'
            )
        )
        root_component_version: str = langchain_core.pydantic_v1.Field(
            description=(
                'Version of the component which serves as root for the component references Tree.'
                ' "greatest" for most recent version.'
            )
        )
        severities: list[
            typing.Literal['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
        ] = langchain_core.pydantic_v1.Field(
            description='Severity levels for which should be queried.',
        )

    class GetTransitiveReferencesWithVulnerability(langchain.tools.BaseTool):
        name = 'get_transitive_references_with_vulnerability'
        description = (
            'A tool that return all transitive references of a specific root component,'
            ' which have a security Vulnerability.'
        )
        args_schema: typing.Type[
            langchain_core.pydantic_v1.BaseModel
        ] | None = GetTransitiveReferencesWithVulnerabilitySchema

        def _run(
            self,
            root_component_name: str,
            root_component_version: str,
            severities: list[typing.Literal['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']]
        ):

            if root_component_version == 'greatest':
                root_component_version = components.greatest_version_if_none(
                    component_name=root_component_name,
                    version=None,
                    version_lookup=component_version_lookup,
                    version_filter=features.VersionFilter.RELEASES_ONLY,
                    invalid_semver_ok=invalid_semver_ok,
                )

            component_references = components.resolve_component_dependencies(
                component_name=root_component_name,
                component_version=root_component_version,
                component_descriptor_lookup=component_descriptor_lookup,
                ctx_repo=None,
            )

            dependency_ids = tuple(
                gci.componentmodel.ComponentIdentity(
                    name=component.component.name,
                    version=component.component.version,
                )
                for component
                in component_references
            )

            findings_query = db_session.query(
                deliverydb.model.ArtefactMetaData.component_name,
                deliverydb.model.ArtefactMetaData.component_version,
                deliverydb.model.ArtefactMetaData.data.op('->>')('severity'),
            ).filter(
                deliverydb.model.ArtefactMetaData.type == dso.model.Datatype.VULNERABILITY,
                sqlalchemy.or_(deliverydb.util.ArtefactMetadataQueries.component_queries(
                    components=dependency_ids,
                )),
                deliverydb.model.ArtefactMetaData.data.op('->>')('severity').in_(severities)
            )

            findings_raw = findings_query.all()
            findings = set(
                f'name: {raw[0]} / version: {raw[1]} / severity: {raw[2]}'
                for raw in findings_raw
            )

            return findings


    class GetAllComponentsWithCVESchema(langchain_core.pydantic_v1.BaseModel):
        cve: str = langchain_core.pydantic_v1.Field(description='CVE of interest.')
        pagination_page: int = langchain_core.pydantic_v1.Field(
            description='Pagination page, starts at page 1',
            default=1
        )

    class GetAllComponentsWithCVE(langchain.tools.BaseTool):
        name = 'get_all_components_with_cve'
        description = (
            'A tool returns all components which are affected by a specific CVE.'
            ' For the sake of performance, it paginates the results in the size of 100 entries.'
        )
        args_schema: typing.Type[
            langchain_core.pydantic_v1.BaseModel
        ] | None = GetAllComponentsWithCVESchema

        def _run(
            self,
            cve: str,
            pagination_page,
        ):

            cve_pattern = r'^CVE-\d{4}-\d{1,}$'
            valid_pattern = bool(re.match(cve_pattern, cve))
            if not valid_pattern:
                return 'Please provide a valid CVE with the following pattern: ^CVE-\d{4}-\d{1,}$'

            total_results = db_session.query(
                deliverydb.model.ArtefactMetaData.component_name,
                deliverydb.model.ArtefactMetaData.component_version,
            ).filter(
                deliverydb.model.ArtefactMetaData.type == dso.model.Datatype.VULNERABILITY,
                deliverydb.model.ArtefactMetaData.data.op('->>')('cve') == cve,
            ).order_by(
                deliverydb.model.ArtefactMetaData.component_name,
            ).group_by(
                deliverydb.model.ArtefactMetaData.component_name,
                deliverydb.model.ArtefactMetaData.component_version,
            ).count()

            print(total_results)

            findings_query = db_session.query(
                deliverydb.model.ArtefactMetaData.component_name,
                deliverydb.model.ArtefactMetaData.component_version,
            ).filter(
                deliverydb.model.ArtefactMetaData.type == dso.model.Datatype.VULNERABILITY,
                deliverydb.model.ArtefactMetaData.data.op('->>')('cve') == cve,
            ).order_by(
                deliverydb.model.ArtefactMetaData.component_name,
            ).group_by(
                deliverydb.model.ArtefactMetaData.component_name,
                deliverydb.model.ArtefactMetaData.component_version,
            ).offset(
                100 * (pagination_page - 1),
            ).limit(
                100,
            )

            findings_raw = findings_query.all()
            pprint.pprint(findings_raw)

            return {
                'findings': findings_raw,
                'page': pagination_page,
                'total_pages': math.ceil(total_results / 100),
            }

    return [
        GetVulnerabilityFindingsForComponents(),
        GetAllComponentsWithCVE(),
        GetTransitiveReferencesWithVulnerability(),
    ]


def get_malware_tools(
    db_session: sqlalchemy.orm.session.Session,
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
    component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
    github_api_lookup,
    invalid_semver_ok: bool=False,
) -> list[langchain.tools.BaseTool]:

    class GetMalwareFindingsForComponentSchema(langchain_core.pydantic_v1.BaseModel):
        component_name: str = langchain_core.pydantic_v1.Field(description="Component Name")
        component_version: str = langchain_core.pydantic_v1.Field(
            description="Component Version, 'greatest' for the newest one or a specific version"
        )

    class GetMalwareFindingsForComponent(langchain.tools.BaseTool):
        name = 'get_malware_findings_for_component'
        description = (
            'A tool that returns the findings of a specific type or types for specific component'
        )
        args_schema: typing.Type[
            langchain_core.pydantic_v1.BaseModel
        ] | None = GetMalwareFindingsForComponentSchema

        def _run(
            self,
            component_name: str,
            component_version: str,
        ):
            if component_version == 'greatest':
                component_version = components.greatest_version_if_none(
                    component_name=component_name,
                    version=None,
                    version_lookup=component_version_lookup,
                    version_filter=features.VersionFilter.RELEASES_ONLY,
                    invalid_semver_ok=invalid_semver_ok,
                )

            component_id = gci.componentmodel.ComponentIdentity(
                name=component_name,
                version=component_version,
            )

            findings_query = db_session.query(deliverydb.model.ArtefactMetaData).filter(
                sqlalchemy.or_(deliverydb.util.ArtefactMetadataQueries.component_queries(
                    components=(component_id,)
                )),
                deliverydb.model.ArtefactMetaData.type.__eq__(dso.model.Datatype.MALWARE),
            )

            findings_raw = findings_query.all()
            findings = [
                deliverydb.util.db_artefact_metadata_to_dso(raw)
                for raw in findings_raw
            ]

            return [{
                f'{finding.artefact.component_name}:{finding.artefact.component_version}': finding.data
            } for finding in findings]

    return [
        GetMalwareFindingsForComponent(),
    ]


def get_license_tools(
    db_session: sqlalchemy.orm.session.Session,
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
    component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
    github_api_lookup,
    invalid_semver_ok: bool=False,
) -> list[langchain.tools.BaseTool]:

    class GetLicenseFindingsForComponentSchema(langchain_core.pydantic_v1.BaseModel):
        component_name: str = langchain_core.pydantic_v1.Field(description="Component Name")
        component_version: str = langchain_core.pydantic_v1.Field(
            description="Component Version, 'greatest' for the newest one or a specific version"
        )

    class GetLicenseFindingsForComponent(langchain.tools.BaseTool):
        name = 'get_license_findings_for_component'
        description = (
            'A tool that returns the findings of a specific type or types for specific component'
        )
        args_schema: typing.Type[
            langchain_core.pydantic_v1.BaseModel
        ] | None = GetLicenseFindingsForComponentSchema

        def _run(
            self,
            component_name: str,
            component_version: str,
        ):
            if component_version == 'greatest':
                component_version = components.greatest_version_if_none(
                    component_name=component_name,
                    version=None,
                    version_lookup=component_version_lookup,
                    version_filter=features.VersionFilter.RELEASES_ONLY,
                    invalid_semver_ok=invalid_semver_ok,
                )

            component_id = gci.componentmodel.ComponentIdentity(
                name=component_name,
                version=component_version,
            )

            findings_query = db_session.query(deliverydb.model.ArtefactMetaData).filter(
                sqlalchemy.or_(deliverydb.util.ArtefactMetadataQueries.component_queries(
                    components=(component_id,)
                )),
                deliverydb.model.ArtefactMetaData.type == dso.model.Datatype.LICENSE,
            )

            findings_raw = findings_query.all()
            findings = [
                deliverydb.util.db_artefact_metadata_to_dso(raw)
                for raw in findings_raw
            ]

            pprint.pprint([{
                f'{finding.artefact.component_name}:{finding.artefact.component_version}': finding.data
            } for finding in findings])

            return [{
                f'{finding.artefact.component_name}:{finding.artefact.component_version}': finding.data
            } for finding in findings]

    return [
        GetLicenseFindingsForComponent(),
    ]


def get_end_of_life_tools(
    db_session: sqlalchemy.orm.session.Session,
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
    component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
    github_api_lookup,
    invalid_semver_ok: bool=False,
) -> list[langchain.tools.BaseTool]:
    print("")
    return []
