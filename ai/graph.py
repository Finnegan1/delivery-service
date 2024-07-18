import json
import os

import langchain_core.output_parsers
import langchain_core.prompts
import langchain_core.pydantic_v1
import langchain_openai
import langgraph.checkpoint.sqlite
import langgraph.graph
import sqlalchemy.orm.session

import ai.graph
import ai.main_nodes.component_agent
import ai.ai_constants
import ai.ai_constants
import ai.state
import ai.state
import components
import gci.componentmodel

OPEN_AI_MODEL: str = os.getenv('OPEN_AI_MODEL') # type: ignore

#-------------------------
# AGENT: GoalDecider
#-------------------------

class GoalResult(langchain_core.pydantic_v1.BaseModel):
  goal: ai.ai_constants.GOAL_TYPES_LITERAL = langchain_core.pydantic_v1.Field(
      description='Describes, which kind of data, the user wants at the end.'
  )
class GoalDecider:
  def __init__(
    self,
  ):
    json_parser = langchain_core.output_parsers.JsonOutputParser(pydantic_object=GoalResult)
    llm = langchain_openai.AzureChatOpenAI(
      model=OPEN_AI_MODEL,
      temperature=0.0,
    ).bind(
      response_format={"type": "json_object"}
    )
    goal_decider_prompt = langchain_core.prompts.ChatPromptTemplate.from_messages(
      [
        (
          'system',
          'You are a Goal Decider. Your task is to analyze, which goal a user question has.'
          ' With goal, is is meant, which result does the user want at the end.'
          ' You can imagine it like the following question:\n'
          'What kind of data should fill an resulting table?\n'
          'You have the following data types to choose from:\n'
          '{datatypes}\n\n'
          'Please output your result in the following JSON format:'
          '{format_instructions}'
        ),
        (
          'human',
          '{question}'
        )
      ]
    ).partial(
      format_instructions=json_parser.get_format_instructions(),
      datatypes=[str(option) for option in ai.ai_constants.GOAL_TYPES_LITERAL.__args__]
    )

    self.runnable = (
      goal_decider_prompt
      | llm
      | json_parser
    )

  def __call__(
    self,
    state: ai.state.State
  ) -> ai.state.State:
    print('--------start Goal Decider--------')
    goal_result: GoalResult = GoalResult(**self.runnable.invoke(
      input={
        'question': state['question'],
      }
    ))
    print('--------Result--------')
    print(json.dumps({
        'goal_type': goal_result.goal
    }, indent=2))
    print('----------------------')
    return {
      'goal_type': goal_result.goal
    } # type: ignore

def goal_to_filterer(state: ai.state.State):
  if(state['goal_type']) == 'components':
    return 'component_agent'
  return 'component_agent'

def build_graph(
  landscape_components: list[gci.componentmodel.Component],
  db_session: sqlalchemy.orm.session.Session,
):  
  
  builder = langgraph.graph.StateGraph(ai.state.State)
  builder.add_node(
    'goal_decider',
    GoalDecider()
  )
  builder.add_node(
    'component_agent',
    ai.main_nodes.component_agent.ComponentAgent(
      landscape_components=landscape_components,
      db_session=db_session,
    )
  )
  
  builder.set_entry_point('goal_decider')
  builder.add_conditional_edges(
    'goal_decider',
    goal_to_filterer,
  )
  builder.set_finish_point('component_agent')
  

  #memory = langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string("checkpoints.sqlite")
  memory = langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string(":memory:")

  graph = builder.compile(checkpointer=memory)
  print('==========Graph Created==========')
  print(graph.get_graph().draw_mermaid())
  print('=================================')
  
  return graph


     