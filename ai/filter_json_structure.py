from __future__ import annotations
import json

def generate_filter_json_structure(filter_options):
    # Initialize the JSON structure
    json_structure = {
        "filters": {
            "description": "A complex filter object used to apply multiple question-based filters with logical operators",
            "type": "object",
            "properties": {
                "AND": {
                    "description": "A list of conditions where all must be true (logical AND)",
                    "type": "array",
                    "items": {
                        "$ref": "#/definitions/condition"
                    }
                },
                "OR": {
                    "description": "A list of conditions where at least one must be true (logical OR)",
                    "type": "array",
                    "items": {
                        "$ref": "#/definitions/condition"
                    }
                },
                "XOR": {
                    "description": "A list of conditions where exactly one must be true (logical XOR)",
                    "type": "array",
                    "items": {
                        "$ref": "#/definitions/condition"
                    }
                },
                "NOT": {
                    "description": "A single condition that must not be true (logical NOT)",
                    "type": "array",
                    "items": {
                        "$ref": "#/definitions/condition"
                    }
                }
            },
            "definitions": {
                "condition": {
                    "description": "A filter condition which can be an question-based filter or another logical operator",
                    "type": "object",
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {
                                "filter_name": {
                                    "description": "The name of the filter.",
                                    "type": "string",
                                    "enum": [],
                                    "enumDescriptions": []
                                },
                                "question": {
                                    "description": "A Question, this filter should answer. Question has to contain all important information for filter.",
                                    "type": "string"
                                }
                            },
                            "required": ["filter_name", "question"]
                        },
                        {
                            "type": "object",
                            "properties": {
                                "AND": {
                                    "description": "A list of conditions where all must be true (logical AND)",
                                    "type": "array",
                                    "items": {
                                        "$ref": "#/definitions/condition"
                                    }
                                },
                                "OR": {
                                    "description": "A list of conditions where at least one must be true (logical OR)",
                                    "type": "array",
                                    "items": {
                                        "$ref": "#/definitions/condition"
                                    }
                                },
                                "XOR": {
                                    "description": "A list of conditions where exactly one must be true (logical XOR)",
                                    "type": "array",
                                    "items": {
                                        "$ref": "#/definitions/condition"
                                    }
                                },
                                "NOT": {
                                    "description": "A single condition that must not be true (logical NOT)",
                                    "type": "array",
                                    "items": {
                                        "$ref": "#/definitions/condition"
                                    }
                                }
                            }
                        }
                    ]
                }
            },
            "additionalProperties": False
        }
    }

    # Add filter options descriptions to the condition definition
    for filter_option in filter_options:
        name = filter_option["name"]
        description = filter_option["description"]
        json_structure["filters"]["definitions"]["condition"]["oneOf"][0]["properties"]["filter_name"]["enum"].append(name)
        json_structure["filters"]["definitions"]["condition"]["oneOf"][0]["properties"]["filter_name"]["enumDescriptions"].append(description)

    return json_structure

if __name__ == '__main__':
  # Example usage
  filter_options = [
      {"name": "resource", "description": "Filter by the resource on which components depend"},
      {"name": "vulnerability", "description": "Filter by specific vulnerabilities in components"},
      {"name": "malware", "description": "Filter by the presence of malware in components"},
  ]
  print(json.dumps(generate_filter_json_structure(filter_options), indent=2))
  
  

from pydantic import BaseModel, Field
from typing import List, Union, Optional
import typing

class Filter(BaseModel):
    filter_name: str = Field(..., description="The name of the attribute to filter on.")
    instruction: str = Field(..., description="The specific instruction related to this filter. Should be a sentence. Instrct only what the entity should have.")
  
class OperatorNOT(BaseModel):
    logical_operator: typing.Literal['NOT'] = 'NOT'
    filterA: Union[Filter, 'OperatorNOT', 'OperatorOR', 'OperatorAND'] = Field(..., description="The Resulting list of this Filter or oprtation will be subtracted with the resulting list of filter B")
    filterB: Union[Filter, 'OperatorNOT', 'OperatorOR', 'OperatorAND'] = Field(..., description="The Resulting list of this Filter or oprtation will be subtracted drom the result of filter A")

class OperatorOR(BaseModel):
    logical_operator: typing.Literal['OR'] = 'OR'
    filter: Union[list[Filter], list['OperatorNOT'], list['OperatorOR'], list['OperatorAND']] = Field(..., description="A list of conditions or Filters whose resulting lists will be meged together with the union operator.")
  
class OperatorAND(BaseModel):
    logical_operator: typing.Literal['AND'] = 'AND'
    filter: Union[list[Filter], list['OperatorNOT'], list['OperatorOR'], list['OperatorAND']] = Field(..., description="A list of conditions or Filters whose resulting lists will be meged together with the intersect operator.")  
class FilterJsonStruckture(BaseModel):
    filter: OperatorNOT | OperatorOR |  OperatorAND | None = Field(None, description='A complex filter object used to apply multiple filters with logical operators')

OperatorNOT.model_rebuild()
OperatorOR.model_rebuild()
OperatorAND.model_rebuild()
FilterJsonStruckture.model_rebuild()


class Conditions(BaseModel):
    AND: Optional[List[Union[Filter, Conditions]]] = Field(None, description="A list of conditions or Filters where all must be true (logical AND)")
    OR: Optional[List[Union[Filter, Conditions]]] = Field(None, description="A list of conditions or Filters where at least one must be true (logical OR)")
    XOR: Optional[List[Union[Filter, Conditions]]] = Field(None, description="A list of conditions or Filters where exactly one must be true (logical XOR)")
    NOT: Optional[List[Union[Filter, Conditions]]] = Field(None, description="A list condition or Filters that must not be true (logical NOT)")
        
#class FilterJsonStruckture(BaseModel):
#    filters: Conditions = Field(None, description='A complex filter object used to apply multiple filters with logical operators')
    
# Update forward references after the class definition  
#Conditions.model_rebuild()