"""
EvalCase definitions for the weather agent eval suite.

All cases are defined in the shared examples/evaluation/samples.py and
re-exported here so test1 imports remain unchanged.
"""

from ..samples import (  # noqa: F401  (re-exports)
    ALL_CASES,
    CAPITAL_QUESTION,
    EVAL_SET,
    HAPPY_PATH_CASES,
    LONDON,
    MULTI_CITY,
    MULTI_CITY_CASES,
    NO_TOOL_CASES,
    NYC,
    TOKYO,
)
