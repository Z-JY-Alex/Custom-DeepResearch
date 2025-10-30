"""
Agent基类测试模块
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agent.base import (
    BaseAgent, SimpleAgent, SearchAgent, CodeAgent,
    AgentTask, TaskExecutionResult, ExecutionMode,
    AgentMemory
)
from backend.agent.schema import AgentState, AgentTypes
from backend.tools.base import BaseTool, ToolFunction, ToolCallResult
from backend.llm.base import LLMConfig, Message, MessageRole
from backend.prompts.base import BasePrompt


class MockTool(BaseTool):
    """模拟工具用于测试"""
    name: str = "mock_tool"
    description: str = "测试用的模拟工具"
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "查询内容"}
        },
        "required": ["query"]
    }
    
    async def execute(self, query: str = "", **kwargs) -> ToolCallResult:
        return ToolCallResult(
            tool_call_id="test_id",
            result=f"Mock result for: {query}",
            output={"mock_data": query}
        )


class TestAgent(SimpleAgent):
    """测试用的简单Agent"""
    
    def __init__(self, **kwargs):
        super().__init__(
            name="TestAgent",
            description="测试用Agent", 
            agent_type=AgentTypes.SUMMARY,
            **kwargs
        )


class TestBaseAgent:
    """BaseAgent基类测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.agent = TestAgent()
        self.mock_tool = MockTool()
        self.agent.add_tool(self.mock_tool)
    
    def test_agent_initialization(self):
        """测试Agent初始化"""
        assert self.agent.name == "TestAgent"
        assert self.agent.description == "测试用Agent"
        assert self.agent.agent_type == AgentTypes.SUMMARY
        assert self.agent.state == AgentState.IDLE
        assert isinstance(self.agent.memory, AgentMemory)
        assert len(self.agent.tools) == 1
    
    def test_prompt_creation(self):
        """测试Prompt创建"""
        prompt = self.agent.create_prompt(
            role="测试助手",
            current_task_description="测试任务",
            context_info={"test": "data"}
        )
        
        assert isinstance(prompt, BasePrompt)
        assert prompt.role == "测试助手"
        assert prompt.current_task_description == "测试任务"
        assert prompt.context_info["test"] == "data"
    
    def test_tool_management(self):
        """测试工具管理"""
        # 测试获取工具
        tool = self.agent.get_tool_by_name("mock_tool")
        assert tool is not None
        assert tool.name == "mock_tool"
        
        # 测试列出工具
        tools = self.agent.list_tools()
        assert "mock_tool" in tools
        
        # 测试移除工具
        removed = self.agent.remove_tool("mock_tool")
        assert removed is True
        assert len(self.agent.tools) == 0
        
        # 重新添加工具用于后续测试
        self.agent.add_tool(self.mock_tool)
    
    def test_state_management(self):
        """测试状态管理"""
        # 初始状态
        assert self.agent.is_idle()
        assert not self.agent.is_running()
        assert not self.agent.is_finished()
        assert not self.agent.is_error()
        
        # 改变状态
        self.agent.set_state(AgentState.RUNNING)
        assert self.agent.is_running()
        assert not self.agent.is_idle()
        
        self.agent.set_state(AgentState.ERROR)
        assert self.agent.is_error()
        
        self.agent.set_state(AgentState.FINISHED)
        assert self.agent.is_finished()
    
    def test_memory_management(self):
        """测试记忆管理"""
        # 添加消息
        message = Message(role=MessageRole.USER, content="测试消息")
        self.agent.memory.add_message(message)
        
        assert len(self.agent.memory.messages) == 1
        assert self.agent.memory.messages[0].content == "测试消息"
        
        # 获取最近消息
        recent = self.agent.memory.get_recent_messages(1)
        assert len(recent) == 1
        assert recent[0].content == "测试消息"
        
        # 清除记忆
        self.agent.clear_memory()
        assert len(self.agent.memory.messages) == 0
    
    def test_agent_info(self):
        """测试获取Agent信息"""
        info = self.agent.get_agent_info()
        
        assert info["name"] == "TestAgent"
        assert info["description"] == "测试用Agent"
        assert info["agent_type"] == AgentTypes.SUMMARY
        assert info["state"] == AgentState.IDLE
        assert "mock_tool" in info["tools"]
        assert "memory_stats" in info


class TestTaskExecution:
    """任务执行测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.agent = TestAgent()
        self.mock_tool = MockTool()
        self.agent.add_tool(self.mock_tool)
    
    def test_task_creation(self):
        """测试任务创建"""
        task = AgentTask(
            name="测试任务",
            description="这是一个测试任务",
            context={"test": "data"}
        )
        
        assert task.name == "测试任务"
        assert task.description == "这是一个测试任务"
        assert task.context["test"] == "data"
        assert task.task_id is not None
        assert len(task.dependencies) == 0
    
    @pytest.mark.asyncio
    async def test_single_task_execution(self):
        """测试单个任务执行"""
        task = AgentTask(
            name="测试任务",
            description="执行测试",
            context={"test": "data"}
        )
        
        # 模拟LLM响应
        self.agent.llm = AsyncMock()
        self.agent.llm.generate = AsyncMock(return_value="任务执行完成")
        
        result = await self.agent.execute_task(task)
        
        assert isinstance(result, TaskExecutionResult)
        assert result.success is True
        assert result.task_id == task.task_id
        assert result.execution_time >= 0
    
    @pytest.mark.asyncio
    async def test_serial_execution(self):
        """测试串行执行"""
        tasks = [
            AgentTask(name="任务1", description="第一个任务"),
            AgentTask(name="任务2", description="第二个任务"),
            AgentTask(name="任务3", description="第三个任务")
        ]
        
        # 模拟LLM响应
        self.agent.llm = AsyncMock()
        self.agent.llm.generate = AsyncMock(return_value="任务执行完成")
        
        results = await self.agent.execute_tasks_serial(tasks)
        
        assert len(results) == 3
        assert all(result.success for result in results)
        assert all(isinstance(result, TaskExecutionResult) for result in results)
    
    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """测试并行执行"""
        tasks = [
            AgentTask(name="任务1", description="第一个任务"),
            AgentTask(name="任务2", description="第二个任务"),
            AgentTask(name="任务3", description="第三个任务")
        ]
        
        # 模拟LLM响应
        self.agent.llm = AsyncMock()
        self.agent.llm.generate = AsyncMock(return_value="任务执行完成")
        
        results = await self.agent.execute_tasks_parallel(tasks, max_concurrent=2)
        
        assert len(results) == 3
        assert all(result.success for result in results)
        assert all(isinstance(result, TaskExecutionResult) for result in results)
    
    @pytest.mark.asyncio
    async def test_loop_execution(self):
        """测试循环执行"""
        tasks = [
            AgentTask(name="循环任务", description="循环执行的任务")
        ]
        
        # 模拟LLM响应
        self.agent.llm = AsyncMock()
        self.agent.llm.generate = AsyncMock(return_value="任务执行完成")
        
        # 定义跳出条件：执行2次后停止
        iteration_count = 0
        def break_condition(results):
            nonlocal iteration_count
            iteration_count += 1
            return iteration_count >= 2
        
        all_results = await self.agent.execute_tasks_loop(
            tasks, 
            max_iterations=5, 
            break_condition=break_condition
        )
        
        assert len(all_results) == 2  # 执行了2次迭代
        assert all(len(iteration_results) == 1 for iteration_results in all_results)
        assert all(
            result.success for iteration_results in all_results 
            for result in iteration_results
        )
    
    @pytest.mark.asyncio
    async def test_workflow_execution(self):
        """测试工作流执行"""
        tasks1 = [AgentTask(name="阶段1任务1", description="第一阶段任务")]
        tasks2 = [AgentTask(name="阶段2任务1", description="第二阶段任务")]
        
        workflow = {
            "name": "测试工作流",
            "stages": [
                {
                    "name": "阶段1",
                    "mode": "serial",
                    "tasks": tasks1
                },
                {
                    "name": "阶段2", 
                    "mode": "parallel",
                    "tasks": tasks2,
                    "max_concurrent": 1
                }
            ]
        }
        
        # 模拟LLM响应
        self.agent.llm = AsyncMock()
        self.agent.llm.generate = AsyncMock(return_value="任务执行完成")
        
        result = await self.agent.execute_workflow(workflow)
        
        assert result["success"] is True
        assert len(result["stages"]) == 2
        assert result["stages"][0]["name"] == "阶段1"
        assert result["stages"][1]["name"] == "阶段2"
        assert result["workflow_id"] is not None


class TestSpecificAgents:
    """特定Agent类型测试"""
    
    @pytest.mark.asyncio
    async def test_search_agent(self):
        """测试搜索Agent"""
        # 创建搜索工具的模拟
        search_tool = MockTool()
        search_tool.name = "tavily_search"
        
        agent = SearchAgent(
            name="SearchAgent",
            description="搜索Agent"
        )
        agent.add_tool(search_tool)
        
        task = AgentTask(
            name="搜索任务",
            description="搜索测试",
            context={"query": "测试搜索"}
        )
        
        result = await agent._execute_task_logic(task)
        
        assert result["task_id"] == task.task_id
        assert result["query"] == "测试搜索"
        assert "search_result" in result
    
    @pytest.mark.asyncio
    async def test_code_agent(self):
        """测试代码Agent"""
        agent = CodeAgent(
            name="CodeAgent",
            description="代码Agent"
        )
        
        # 模拟LLM响应
        agent.llm = AsyncMock()
        agent.llm.generate = AsyncMock(return_value="生成的代码内容")
        
        task = AgentTask(
            name="代码任务",
            description="生成代码",
            context={"language": "python"}
        )
        
        result = await agent._execute_task_logic(task)
        
        assert result["task_id"] == task.task_id
        assert result["task_name"] == "代码任务"
        assert "code_response" in result


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])