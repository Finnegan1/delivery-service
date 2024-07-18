import os
import typing

OPEN_AI_MODEL: str = os.getenv('OPEN_AI_MODEL') # type: ignore
GOAL_TYPES_LITERAL = typing.Literal['components', 'malware', 'vulnerabilities', 'resources', 'packages', 'os', 'none_of_the_others']
