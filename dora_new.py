import collections
import collections.abc
import concurrent.futures
import dataclasses
import datetime
import functools
import pprint
from re import I
import statistics
import typing
import urllib.parse

import cachetools.keys
import dateutil.parser
from dora_result_calcs import ReturnCommitObject, ReturnDeploymentObject, ReturnObject
import dora_result_calcs
import falcon
import falcon.media.validators
import github3

import ci.util
import cnudie.retrieve
import cnudie.util
import gci.componentmodel as cm
from numpy import median
import semver
import version as versionutil

import caching
import components
import middleware
import middleware.auth


def _cache_key_gen_all_versions_sorted(
    component: cnudie.retrieve.ComponentName,
    version_lookup: cnudie.retrieve.VersionLookupByComponent,
    only_releases: bool = True,
    invalid_semver_ok: bool = False,
    sorting_direction: typing.Literal['asc', 'desc'] = 'desc',
):
    return cachetools.keys.hashkey(
        cnudie.util.to_component_name(component),
        only_releases,
        invalid_semver_ok,
        sorting_direction,
    )


@caching.cached(
    cache=caching.TTLFilesystemCache(ttl=60 * 60 * 24, max_total_size_mib=128), # 1 day
    key_func=_cache_key_gen_all_versions_sorted,
)
def all_versions_sorted(
    component: cnudie.retrieve.ComponentName,
    version_lookup: cnudie.retrieve.VersionLookupByComponent,
    only_releases: bool = True,
    invalid_semver_ok: bool = False,
    sorting_direction: typing.Literal['asc', 'desc'] = 'desc'
) -> list[str]:
    '''
    This is a convenience function for looking up all versions of a specific
    component.

    asc-sorting means old to new => [0.102.0 ... 0.321.2]
    desc-sorting means new to old => [0.321.2 ... 0.102.0]
    '''
    component_name = cnudie.util.to_component_name(component)

    def filter_version(version: str, invalid_semver_ok: bool, only_releases:bool):
        if not (parsed_version := versionutil.parse_to_semver(
            version=version,
            invalid_semver_ok=invalid_semver_ok,
        )):
            return False

        if only_releases:
            return versionutil.is_final(parsed_version)

        return True

    versions = (
        version for version
        in version_lookup(component_name)
        if filter_version(version, invalid_semver_ok, only_releases)
    )

    versions = sorted(
        versions,
        key=lambda v: versionutil.parse_to_semver(
            version=v,
            invalid_semver_ok=invalid_semver_ok,
        ),
        reverse=sorting_direction == 'desc',
    )

    return versions


def filter_component_versions_newer_than_date(
        component: cnudie.retrieve.ComponentName,
        all_versions: list[semver.VersionInfo],
        date: datetime.datetime,
        component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
) -> list[semver.VersionInfo]:
    all_versions = sorted(
        all_versions,
        key=lambda v: versionutil.parse_to_semver(v),
        reverse=True,
    )

    component_versions: list[semver.VersionInfo] = []

    for version in all_versions:
        descriptor: cm.ComponentDescriptor = component_descriptor_lookup(
            cm.ComponentIdentity(
                name=cnudie.util.to_component_name(component),
                version=version,
            )
        )
        creation_date = components.get_creation_date(descriptor.component)

        date = date.astimezone(datetime.timezone.utc)
        creation_date = creation_date.astimezone(datetime.timezone.utc)

        if creation_date > date:
            component_versions.append(version)
        else:
            break

    return component_versions


def _cache_key_gen_get_all_components_in_tree_hightes_verison(
    component: cnudie.retrieve.ComponentName,
    component_version: semver.VersionInfo,
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
):
    return cachetools.keys.hashkey(
        cnudie.util.to_component_name(component),
        component_version.to_tuple(),
    )


@caching.cached(
    cache=caching.LFUFilesystemCache(max_total_size_mib=512),
    key_func=_cache_key_gen_get_all_components_in_tree_hightes_verison,
)
def get_all_components_in_tree_hightes_verison(
    component: cnudie.retrieve.ComponentName,
    component_version: semver.VersionInfo,
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
) -> dict[str, cm.Component]:
    '''
    return dict with all components of the component tree
    key: component name
    value: highest version of the component
    '''
    def default_factory():
        return None
    components_by_name = collections.defaultdict(default_factory)

    descriptor = component_descriptor_lookup(
        cm.ComponentIdentity(
            name=cnudie.util.to_component_name(component),
            version=component_version,
        )
    )
    if not descriptor:
        raise falcon.HTTPNotFound(
            title='Component not found',
            description='Component not found',
        )
        
    components_list = [
        c.component
        for c in cnudie.iter.iter(
            component=descriptor.component,
            lookup=component_descriptor_lookup,
            node_filter=cnudie.iter.Filter.components,
        )
    ]

    def version_key(c):
        if c is not None:
            return versionutil.parse_to_semver(c.version)
        else:
            return semver.VersionInfo(0, 0, 0)

    for component in components_list:
        components_by_name[component.name] = max(
            components_by_name[component.name],
            component,
            key=version_key,
        )

    return dict(components_by_name)


def highest_version(
    versions: list[semver.VersionInfo],
):
    return max(versions)


def compar_versions_of_component_in_tree(
    tree_root_component: cnudie.retrieve.ComponentName,
    component_version_older: semver.VersionInfo,
    component_version_newer: semver.VersionInfo,
    referenced_component: cnudie.retrieve.ComponentName,
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
) -> tuple[str, str]:

    component_old = component_descriptor_lookup(
        cm.ComponentIdentity(
            name=cnudie.util.to_component_name(tree_root_component),
            version=component_version_older,
        )
    ).component
    
    component_new = component_descriptor_lookup(
        cm.ComponentIdentity(
            name=cnudie.util.to_component_name(tree_root_component),
            version=component_version_newer,
        )
    ).component
    
    if not component_old or not component_new:
        raise falcon.HTTPNotFound(
            title='Component not found',
            description='Component not found',
        )

    component_tree_old = get_all_components_in_tree_hightes_verison(
        component=component_old.name,
        component_version=versionutil.parse_to_semver(component_old.version),
        component_descriptor_lookup=component_descriptor_lookup,
    )

    component_tree_new = get_all_components_in_tree_hightes_verison(
        component=component_new.name,
        component_version=versionutil.parse_to_semver(component_new.version),
        component_descriptor_lookup=component_descriptor_lookup,
    )
    
    if not component_tree_old or not component_tree_new:
        raise falcon.HTTPNotFound(
            title='Reference not found',
            description='Reference not found',
        )

    referenced_component_old = component_tree_old[referenced_component]
    referenced_component_new = component_tree_new[referenced_component]

    return (
        referenced_component_old.version,
        referenced_component_new.version,
    )


@dataclasses.dataclass(frozen=True)
class ComponentVersionChange:
    target_component: cnudie.retrieve.ComponentName
    target_component_versions_older: str
    target_component_versions_newer: str
    referenced_component: cnudie.retrieve.ComponentName
    referenced_component_version_older_release: str
    referenced_component_version_newer_release: str

    def to_dict(self) -> dict[str, typing.Any]:
        return {
            'target_component': cnudie.util.to_component_name(self.target_component),
            'target_component_versions_older': str(self.target_component_versions_older),
            'target_component_versions_newer': str(self.target_component_versions_newer),
            'referenced_component': cnudie.util.to_component_name(self.referenced_component),
            'referenced_component_version_older': str(self.referenced_component_version_older_release),
            'referenced_component_version_newer': str(self.referenced_component_version_newer_release),
        }


###############################################################################
# Lead Time Calculation
###############################################################################


def can_process(dependency_update: components.ComponentVector):
    old_main_source = cnudie.util.main_source(dependency_update.start)
    new_main_source = cnudie.util.main_source(dependency_update.end)

    if (
        not isinstance(old_main_source.access, cm.GithubAccess)
        or not isinstance(new_main_source.access, cm.GithubAccess)
    ):
        return False

    if (
        not isinstance(old_main_source.access.commit, str)
        or not isinstance(new_main_source.access.commit, str)
    ):
        return False

    return True


def _cache_key_gen_component_vector_and_lookup(
    left_commit: str,
    right_commit: str,
    github_repo,
):
    return cachetools.keys.hashkey(
        left_commit,
        right_commit,
    )


@caching.cached(
    cache=caching.LFUFilesystemCache(max_total_size_mib=256),
    key_func=_cache_key_gen_component_vector_and_lookup,
)
def commits_for_component_change(
    left_commit: str,
    right_commit: str,
    github_repo: github3.repos.Repository,
) -> tuple[github3.github.repo.commit.ShortCommit]:
    '''
    returns commits between passed-on commits. results are read from github-api and cached.
    passed-on commits must exist in repository referenced by passed-in github_repo.
    '''
    commits: tuple[github3.github.repo.commit.ShortCommit] = tuple(github_repo.compare_commits(
        left_commit,
        right_commit,
    ).commits())

    return commits


def calculate_lead_time_based_on_deployment_frequency(
    component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
    component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
    github_api_lookup,
    target_component_name: str,
    time_span_days: int,
    filter_component_name: str,
    target_version_changes_with_ref_change: list[ComponentVersionChange],
) -> list[ReturnDeploymentObject]:

    deployment_objects: list[ReturnDeploymentObject] = []

    _github_api = functools.cache(github_api_lookup)

    @functools.cache
    def _github_repo(repo_url: urllib.parse.ParseResult):
        github = _github_api(repo_url)
        org, repo = repo_url.path.strip('/').split('/')
        return github.repository(org, repo)

    def resolve_ref_change_commits(
        target_version_change_with_ref_change: ComponentVersionChange,
    ):
        old_ref_component: cm.Component = component_descriptor_lookup(
            cm.ComponentIdentity(
                name=cnudie.util.to_component_name(target_version_change_with_ref_change.referenced_component),
                version=target_version_change_with_ref_change.referenced_component_version_older_release,
            )
        ).component

        new_ref_component: cm.Component = component_descriptor_lookup(
            cm.ComponentIdentity(
                name=cnudie.util.to_component_name(target_version_change_with_ref_change.referenced_component),
                version=target_version_change_with_ref_change.referenced_component_version_newer_release,
            )
        ).component

        if not old_ref_component or not new_ref_component:
            raise falcon.HTTPNotFound(
                title='Component not found',
                description='Component not found',
            )

        if not can_process(
            components.ComponentVector(
                start=old_ref_component,
                end=new_ref_component,
            )
        ):
            print("can't process")
            return

        old_main_source = cnudie.util.main_source(old_ref_component)
        new_main_source = cnudie.util.main_source(new_ref_component)

        if not old_main_source or not new_main_source:
            print("no main source")
            return

        old_access = old_main_source.access
        new_access = new_main_source.access

        if new_access.type is not cm.AccessType.GITHUB or old_access.type is not cm.AccessType.GITHUB:
            print("no github access")
            return

        old_repo_url = ci.util.urlparse(old_access.repoUrl)
        new_repo_url = ci.util.urlparse(new_access.repoUrl)

        if not old_repo_url == new_repo_url:
            print("repo urls are not equal")
            return # ensure there was no repository-change between component-versions

        old_commit = old_access.commit or old_access.ref
        new_commit = new_access.commit or new_access.ref

        github_repo = _github_repo(
            repo_url=old_repo_url, # already checked for equality; choose either
        )

        commits = commits_for_component_change(
            left_commit=old_commit,
            right_commit=new_commit,
            github_repo=github_repo,
        )

        for commit in commits:
            commit_objects: list[ReturnCommitObject] = []
            deployment_date = components.get_creation_date(
                component_descriptor_lookup(
                    cm.ComponentIdentity(
                        name=cnudie.util.to_component_name(target_component_name),
                        version=target_version_change_with_ref_change.target_component_versions_newer,
                    ),
                ).component
            )
            for commit in commits:
                if (
                    (
                            commit_date := components.ensure_utc(dateutil.parser.isoparse(commit.commit.author['date']))
                    ) > (
                        datetime.datetime.now(datetime.timezone.utc) -
                        datetime.timedelta(days=time_span_days)
                    )
                ):
                    pprint.pprint(commit)
                    commit_objects.append(
                        ReturnCommitObject(
                            commitDate=commit_date,
                            commitSha=commit.sha,
                            deploymentDate=deployment_date,
                            leadTime=(deployment_date - commit_date),
                            url=commit.html_url,
                        ),
                    )

        deployment_objects.append(
            ReturnDeploymentObject(
                targetComponentVersionNew=target_version_change_with_ref_change.target_component_versions_newer,
                targetComponentVersionOld=target_version_change_with_ref_change.target_component_versions_older,
                deployedComponentVersion=target_version_change_with_ref_change.referenced_component_version_newer_release,
                oldComponentVersion=target_version_change_with_ref_change.referenced_component_version_older_release,
                deploymentDate=deployment_date,
                commits=commit_objects
            )
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as tpe:
        futures = {
            tpe.submit(resolve_ref_change_commits, target_version_change_with_ref_change)
            for target_version_change_with_ref_change in target_version_changes_with_ref_change
        }
        concurrent.futures.wait(futures)

    return deployment_objects


@middleware.auth.noauth
class DoraMetricsDeploymentFrequency:
    def __init__(
        self,
        component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
        component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
        github_api_lookup,
    ):
        self._component_descriptor_lookup = component_descriptor_lookup
        self._component_version_lookup = component_version_lookup
        self.github_api_lookup = github_api_lookup

    def on_get(self, req: falcon.Request, resp: falcon.Response):
        target_component_name: str = req.get_param(
            name='target_component_name',
            required=True,
        )
        time_span_days: int = req.get_param_as_int(
            name='time_span_days',
            default=90,
        )
        filter_component_name: str = req.get_param(
            name='filter_component_name',
            required=True,
        )

        components.check_if_component_exists(
            component_name=target_component_name,
            version_lookup=self._component_version_lookup,
            raise_http_error=True,
        )

        components.check_if_component_exists(
            component_name=filter_component_name,
            version_lookup=self._component_version_lookup,
            raise_http_error=True,
        )

        all_target_component_versions = all_versions_sorted(
            component=target_component_name,
            version_lookup=self._component_version_lookup,
        )

        target_component_versions = filter_component_versions_newer_than_date(
            component=target_component_name,
            all_versions=all_target_component_versions,
            date=datetime.datetime.now() - datetime.timedelta(days=time_span_days),
            component_descriptor_lookup=self._component_descriptor_lookup,
        )

        # add the last version out of the date range to the list, else it would not be possible to check if 
        # there where any version changes within the last release within the date range
        if len(target_component_versions) != len(all_target_component_versions):
            target_component_versions.append(all_target_component_versions[len(target_component_versions)])
        # TODO how to handle if first release of target component is within the date range

        target_component_verisons_amount = len(target_component_versions)

        target_version_changes: list[ComponentVersionChange] = []

        for id in range(0, target_component_verisons_amount - 1):
            if id == target_component_verisons_amount - 1:
                break

            target_version_new = target_component_versions[id]
            target_version_old = target_component_versions[id + 1]

            new_target_component = self._component_descriptor_lookup(
                cm.ComponentIdentity(
                    name=cnudie.util.to_component_name(target_component_name),
                    version=versionutil.parse_to_semver(target_version_new),
                )
            ).component

            old_target_component = self._component_descriptor_lookup(
                cm.ComponentIdentity(
                    name=cnudie.util.to_component_name(target_component_name),
                    version=versionutil.parse_to_semver(target_version_old),
                )
            ).component

            if not new_target_component or not old_target_component:
                raise falcon.HTTPNotFound(
                    title='Component not found',
                    description='Component not found',
                )

            reference_versions = compar_versions_of_component_in_tree(
                tree_root_component=cnudie.util.to_component_name(target_component_name),
                component_version_older=versionutil.parse_to_semver(target_version_old),
                component_version_newer=versionutil.parse_to_semver(target_version_new),
                referenced_component=filter_component_name,
                component_descriptor_lookup=self._component_descriptor_lookup,
            )

            target_version_changes.append(
                ComponentVersionChange(
                    target_component=cnudie.util.to_component_name(target_component_name),
                    target_component_versions_older=target_version_old,
                    target_component_versions_newer=target_version_new,
                    referenced_component=cnudie.util.to_component_name(filter_component_name),
                    referenced_component_version_older_release=reference_versions[0],
                    referenced_component_version_newer_release=reference_versions[1],
                )
            )

        changes_per_month = collections.defaultdict(lambda: 0)
        target_version_changes_with_ref_change = []

        for target_version_change in target_version_changes:
            if target_version_change.referenced_component_version_older_release < target_version_change.referenced_component_version_newer_release:
                creation_date = components.get_creation_date(
                    self._component_descriptor_lookup(
                        cm.ComponentIdentity(
                            name=target_version_change.target_component,
                            version=target_version_change.target_component_versions_newer,
                        )
                    ).component
                )
                changes_per_month[creation_date.isoformat()] += 1
                target_version_changes_with_ref_change.append(target_version_change)

        deployment_objects = calculate_lead_time_based_on_deployment_frequency(
            component_descriptor_lookup=self._component_descriptor_lookup,
            component_version_lookup=self._component_version_lookup,
            github_api_lookup=self.github_api_lookup,
            target_component_name=target_component_name,
            time_span_days=time_span_days,
            filter_component_name=filter_component_name,
            target_version_changes_with_ref_change=target_version_changes_with_ref_change,
        )

        deployments_per = dora_result_calcs.calc_deployments_per(
            deployment_objects=deployment_objects,
        )

        median_deployment_frequency = statistics.mean(deployments_per['deploymentsPerMonth'].values())

        lead_time_per = dora_result_calcs.calc_lead_time_per(
            deployment_objects=deployment_objects,
        )

        median_lead_time = statistics.median(
            lead_time_per['medianLeadTimePerMonth'].values()
        )

        return_object = ReturnObject(
            targetComponentName=target_component_name,
            timePeriod=time_span_days,
            componentName=filter_component_name,
            deploymentsPerMonth=deployments_per['deploymentsPerMonth'],
            deploymentsPerWeek=deployments_per['deploymentsPerWeek'],
            deploymentsPerDay=deployments_per['deploymentsPerDay'],
            medianDeploymentFrequency=median_deployment_frequency,
            leadTimePerMonth=lead_time_per['medianLeadTimePerMonth'],
            leadTimePerWeek=lead_time_per['medianLeadTimePerWeek'],
            leadTimePerDay=lead_time_per['medianLeadTimePerDay'],
            medianLeadTime=median_lead_time,
            deployents=deployment_objects
        )

        pprint.pprint(return_object.to_dict())

        resp.media = return_object.to_dict()
