import pprint

import falcon
import langchain_core.messages
import langchain_core.runnables
import langfuse.callback
import langgraph.checkpoint.sqlite
import langgraph.graph
import ai.state
import middleware.auth
from langfuse.openai import openai

import ai.graph
import cnudie.retrieve
import components
import eol
import gci.componentmodel


@middleware.auth.noauth
class AiEndpoint:
    def __init__(
      self,
      component_descriptor_lookup: cnudie.retrieve.ComponentDescriptorLookupById,
      component_version_lookup: cnudie.retrieve.VersionLookupByComponent,
      github_api_lookup,
      eol_client: eol.EolClient,
      invalid_semver_ok: bool=False,
    ):
      self._component_descriptor_lookup = component_descriptor_lookup
      self._component_version_lookup = component_version_lookup
      self.github_api_lookup = github_api_lookup
      self._eol_client = eol_client
      self._invalid_semver_ok = invalid_semver_ok

    def on_post(
      self,
      req: falcon.Request, 
      resp: falcon.Response
    ):

      body = req.media
      question: str = body.get('question')
      root_component_identity_str: str = body.get('rootComponentIdentity')
      
      root_component_identity = gci.componentmodel.ComponentIdentity(
        name=root_component_identity_str.split(':')[0],
        version=root_component_identity_str.split(':')[1],
      )
      
      landscape_components = [
        component_node.component
        for component_node
        in components.resolve_component_dependencies(
            component_name=root_component_identity.name,
            component_version=root_component_identity.version,
            component_descriptor_lookup=self._component_descriptor_lookup,
            ctx_repo=None,
        )
      ]
      
      
      
      resp.media = ''
      
      return
