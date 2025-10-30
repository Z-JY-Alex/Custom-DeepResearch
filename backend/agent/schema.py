from enum import Enum
from typing import List, Any


class AgentState(str, Enum):
    
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


class AgentTypes(str, Enum):
    
    SEARCH = "SEARCH"
    CODE = "CODE"
    SUMMARY = "SUMMARY"
    
    @classmethod
    def to_list(cls) -> List[Any]:
        return [member.value for member in cls]
    
    
class AgentPools(str, Enum):
    """
    Agent 池子(用户Plan分配任务是分配合适的Agent)
    """
    WEB_SEARCH = "WEB_SEARCH"
    CONTENT_ANALYZER = "CONTENT_ANALYSIS"
    TEST_CASE_GENERATE = "TEST_CASE_GENERATE"
    CODE_GENERATE = "CODE_GENERATE"
    
    @classmethod
    def to_list(cls) -> List[Any]:
        return [member.value for member in cls]
