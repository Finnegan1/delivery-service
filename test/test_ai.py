import langchain_core.pydantic_v1

import ai.filter_json_structure
import ai.graph
import ai.main_nodes
import ai.ai_constants

def test_goal_decider():
  class QuestionAndAnswer(langchain_core.pydantic_v1.BaseModel):
    question: str 
    answer: str
    
  test_questions_and_answers: list[QuestionAndAnswer] = [
    QuestionAndAnswer(
      question='Which packages does resource Resource delivery-db-backup use?',
      answer='packages',
    ),
    QuestionAndAnswer(
      question='Which resources depend on package openssh?',
      answer='resources',
    ),
    QuestionAndAnswer(
      question='What vulnerability findings with a high severity affect the component C123?',
      answer='vulnerabilities',
    ),
    QuestionAndAnswer(
      question='Which malware findings where there in the last 10 Days',
      answer='malware',
    ),
    QuestionAndAnswer(
      question='Which packages does resource Resource delivery-db-backup use?',
      answer='packages',
    ),
    QuestionAndAnswer(
      question='List all OCM Components with Resources based on Alpine [based on branch that will expire in less than 30d]',
      answer='components',
    ),
    QuestionAndAnswer(
      question='List all Resources that are affected by CVE-XXX.',
      answer='resources',
    ),
  ]
  
  goal_decider = ai.graph.GoalDecider()
  for test_question_and_answer in test_questions_and_answers:
    input_state: ai.graph.State = {
      'question': test_question_and_answer.question,
      'goal_type': 'none_of_the_others',
    }
    answer = goal_decider.runnable.invoke(input=input_state)
    print(f'{answer['goal']}=={test_question_and_answer.answer}?')
    assert answer['goal'] == test_question_and_answer.answer
    
    
def test_filter_json_structure_creation():

  filter_options = [
      {'name': 'resource', 'description': 'Filter by the resource on which components depend'},
      {'name': 'vulnerability', 'description': 'Filter by specific vulnerabilities in components'},
      {'name': 'malware', 'description': 'Filter by the presence of malware in components'},
  ]
  
  assert ai.filter_json_structure.generate_filter_json_structure(filter_options) == {
    'filters': {
        'description': 'A complex filter object used to apply multiple attribute-based filters with logical operators',
        'type': 'object',
        'properties': {
            'AND': {
                'description': 'A list of conditions where all must be true (logical AND)',
                'type': 'array',
                'items': {'$ref': '#/definitions/condition'},
            },
            'OR': {
                'description': 'A list of conditions where at least one must be true (logical OR)',
                'type': 'array',
                'items': {'$ref': '#/definitions/condition'},
            },
            'XOR': {
                'description': 'A list of conditions where exactly one must be true (logical XOR)',
                'type': 'array',
                'items': {'$ref': '#/definitions/condition'},
            },
            'NOT': {
                'description': 'A single condition that must not be true (logical NOT)',
                'type': 'array',
                'items': {'$ref': '#/definitions/condition'},
            },
        },
        'definitions': {
            'condition': {
                'description': 'A filter condition which can be an attribute-based filter or another logical operator',
                'type': 'object',
                'oneOf': [
                    {
                        'type': 'object',
                        'properties': {
                            'attribute': {
                                'description': 'The name of the attribute to filter on',
                                'type': 'string',
                                'enum': ['resource', 'vulnerability', 'malware'],
                                'enumDescriptions': [
                                    'Filter by the resource on which components depend',
                                    'Filter by specific vulnerabilities in components',
                                    'Filter by the presence of malware in components',
                                ],
                            },
                            'question': {
                                'description': 'The specific question related to this filter',
                                'type': 'string',
                            },
                        },
                        'required': ['attribute', 'question'],
                    },
                    {
                        'type': 'object',
                        'properties': {
                            'AND': {
                                'description': 'A list of conditions where all must be true (logical AND)',
                                'type': 'array',
                                'items': {'$ref': '#/definitions/condition'},
                            },
                            'OR': {
                                'description': 'A list of conditions where at least one must be true (logical OR)',
                                'type': 'array',
                                'items': {'$ref': '#/definitions/condition'},
                            },
                            'XOR': {
                                'description': 'A list of conditions where exactly one must be true (logical XOR)',
                                'type': 'array',
                                'items': {'$ref': '#/definitions/condition'},
                            },
                            'NOT': {
                                'description': 'A single condition that must not be true (logical NOT)',
                                'type': 'array',
                                'items': {'$ref': '#/definitions/condition'},
                            },
                        },
                    },
                ],
            }
        },
        'additionalProperties': False,
    }
}
