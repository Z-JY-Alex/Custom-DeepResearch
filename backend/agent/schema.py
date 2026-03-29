from enum import Enum
from typing import List, Any


class AgentState(str, Enum):

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING_USER_INPUT = "WAITING_USER_INPUT"
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
    SUMMARY_REPORT = "SUMMARY_REPORT"
    DATA_ANALYSIS = "DATA_ANALYSIS"
    
    @classmethod
    def to_list(cls) -> List[Any]:
        return [member.value for member in cls]
