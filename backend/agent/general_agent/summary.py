from datetime import datetime
from typing import Any, AsyncGenerator, List

from loguru import logger
from pydantic import Field

from backend.agent.general_agent.base import BaseAgent
from backend.agent.schema import AgentState
from backend.llm.base import Message, MessageRole
from backend.prompts.summary import (
    SUMMARY_AGENT_INSTRUCTION,
    SUMMARY_AGENT_USER_INSTRUCTION
)


class SummaryAgent(BaseAgent):
    """
    SummaryAgent：负责读取任务执行过程中的资料，生成面向用户的成果总结报告。

    功能特性：
    - 汇总任务核心成果与结论
    - 主动调用文件读取等工具补全关键信息
    - 生成结构化的 Markdown 报告
    """

    agent_name: str = Field(default="SummaryAgent", description="Agent名称")
    agent_description: str = Field(
        default="汇总任务成果并生成结构化报告的总结代理",
        description="Agent描述",
    )

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self.instruction = SUMMARY_AGENT_INSTRUCTION.format(
            CURRENT_TIME=self.current_time,
            WORKDIR=self.work_dir,
            session_id=self.session_id,
        )

        logger.info(f"SummaryAgent {self.agent_id} 初始化完成")

    async def run(self, query: str) -> AsyncGenerator[str, None]:
        if not self.llm:
            raise ValueError("LLM未配置，无法执行SummaryAgent")

        self.state = AgentState.RUNNING
        self.current_round = 0

        # logger.info(f"开始执行总结任务：{query}")

        messages: List[Message] = [
            Message(
                role=MessageRole.ASSISTANT,
                content=self.artifact_manager.show() if self.artifact_manager else "",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"current_round": self.current_round},
            ),
            Message(
                role=MessageRole.SYSTEM,
                content=self.instruction,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"current_round": self.current_round},
            ),
            Message(
                role=MessageRole.USER,
                content=SUMMARY_AGENT_USER_INSTRUCTION.format(
                    user_query=query,
                    session_id=self.session_id,
                    CURRENT_TIME=self.current_time,
                ),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"current_round": self.current_round},
            ),
        ]

        if self.agent_id not in self.memory.states:
            self.memory.states[self.agent_id] = {}

        self.memory.states[self.agent_id]["task"] = query
        self.memory.states[self.agent_id]["all_history"] = messages
        self.memory.states[self.agent_id]["tool_result"] = []

        async for chunk in self._run():
            yield chunk

