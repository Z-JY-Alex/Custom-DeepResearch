import os
import asyncio
from typing import Any, Dict, Optional, List
from loguru import logger
from pydantic import BaseModel, Field
from backend.llm.base import LLMConfig
from backend.memory.base import BaseMemory
from backend.artifacts.manager import ArtifactManager
from backend.tools.base import BaseTool, ToolCallResult, ToolError

AGENT_LIST = ["WEB_SEARCH", "CONTENT_ANALYSIS", "TEST_CASE_GENERATE", "CODE_GENERATE"]

_SUB_AGENT_EXECUTE_DESCRIPTION = """智能选择并调度最合适的子代理来执行特定任务。
此工具会根据任务的类型、复杂度、领域特征和执行要求，自动匹配最适合的专业子代理。
每个子代理都具有特定的专长领域和能力边界，工具会确保任务被分配给最有能力完成的代理。"""

_AGENT_NAME_DESCRIPTION = """
要调用的子代理名称, 可选代理及其核心能力：
- WEB_SEARCH: 网络搜索和信息检索专家
- CONTENT_ANALYSIS: 文档分析、文档内容解读
- TEST_CASE_GENERATE: 测试用例设计和生成专家，**所有涉及测试用例的任务都必须使用此代理**
- CODE_GENERATE: 代码编写和技术实现专家

选择原则：
- 根据任务的核心需求选择最匹配的代理
- **任何涉及测试用例生成、测试用例设计、接口测试分析的任务都必须选择TEST_CASE_GENERATE**
- 考虑代理的专长领域和能力范围
- 评估任务复杂度是否在代理处理能力内
- 如果任务涉及多个领域，选择最核心的那个

**TEST_CASE_GENERATE 必须处理的任务类型：**
- 接口测试用例设计
- 功能测试用例生成
- 接口分析与测试用例设计
- 测试场景设计
- 测试数据设计
- 自动化测试用例规划
- 接口测试覆盖分析

示例选择：
- "查找最新的Python 3.12新特性" → WEB_SEARCH
- "解读产品需求文档并提取核心功能点" → CONTENT_ANALYSIS
- "xxx接口详细分析与用例设计" → TEST_CASE_GENERATE
- "设计登录接口的测试用例" → TEST_CASE_GENERATE
- "生成API接口测试场景" → TEST_CASE_GENERATE
- "实现一个LRU缓存算法" → CODE_GENERATE
"""

_AGENT_TASK_DESCRIPTION = """
要执行的具体任务描述，需要清晰、完整地说明子代理需要完成的工作。

【核心要素】（必需）
- 任务目标：明确说明要达成什么结果
- 输入信息：提供必要的数据、参数或上下文
- 输出要求：说明期望的输出格式、内容结构或质量标准

【上下文关联】（重要）
- 前序任务关联：明确说明当前任务与之前已完成任务的关系
  * 需要使用之前生成的文件、数据或结果时，明确指出具体文件路径和使用方式
  * 需要基于之前任务的输出进行扩展或修改时，说明继承和变更的内容
  * 需要保持与之前任务一致性时，说明需要遵循的标准或规范
- 后续任务适配：考虑当前任务输出对后续任务的支持
  * 如果后续任务需要当前任务的文件，确保输出格式和结构便于后续使用
  * 如果后续任务是相关功能的扩展，预留必要的接口和扩展点
  * 如果后续任务需要执行当前生成的代码，确保代码具备可执行性和完整性

【扩展信息】（建议提供）
- 依赖关系：是否依赖其他任务的结果
- 质量标准：准确性、完整性、可读性等具体要求
- 特殊需求：特定的工具、格式、规范或标准

【针对不同代理的描述建议】
 WEB_SEARCH 任务描述应包含：
- 搜索关键词或主题
- 信息时效性要求（最新、近一年、不限等）
- 信息来源偏好（学术、新闻、官方文档等）
- 信息深度（概览、详细分析、技术细节）
- 期望的信息组织方式（列表、对比、时间线）

CONTENT_UNDERSTANDING 任务描述应包含：
- 待分析的文档来源或内容概述
- 理解目标（提取信息、分析逻辑、发现问题等）
- 关注重点（特定章节、关键字段、业务流程等）
- 输出形式（摘要、结构化列表、关系图、对比表等）
- 分析深度（浅层提取、深度解读、批判性分析）
- 特定关注点（风险、矛盾、遗漏、依赖关系等）

TEST_CASE_GENERATE 任务描述应包含：
- 待测试功能的详细说明或需求文档（**必须包含完整的接口分析**）
- 测试类型（功能、性能、安全、兼容性等）
- 覆盖范围要求（正常、异常、边界、极端）
- 用例格式要求（表格、代码、自然语言描述）
- **如果是接口测试，必须包含接口分析过程和测试用例设计**
- **支持从接口文档分析到测试用例生成的完整流程**

CODE_GENERATE 任务描述应包含：
- 编程语言和技术栈
- 功能需求和业务逻辑
- 性能要求和约束条件
- 代码风格和规范要求
- 是否需要测试代码和文档

**特殊要求：**
- 对于自动化测试相关的代码生成任务：
  * 不需要支持多环境配置（dev/test/prod）
  * 不需要复杂的日志系统和日志配置
  * 专注于测试逻辑的核心实现
  * 保持代码结构简单直接
  * 仅生成必要的测试配置和工具函数

【描述示例】
**好的描述示例**：

WEB_SEARCH:
"搜索2024年AI Agent技术的最新发展趋势，重点关注多代理协作和工具调用能力，
    需要来自技术博客、学术论文和行业报告的信息，整理成按时间线组织的结构化摘要，
    突出标志性进展和主流技术路线"

CONTENT_UNDERSTANDING:
"解读attached的产品需求文档（PRD），提取所有功能模块及其优先级，
    识别各模块之间的依赖关系，分析需求的完整性和一致性，
    重点关注是否存在需求冲突、边界条件未定义或技术可行性问题，
    输出为结构化的功能清单和风险点列表"

TEST_CASE_GENERATE:
"基于附件中的用户登录接口文档，进行完整的接口分析并生成测试用例集，
    包括接口参数分析、响应结构分析、业务规则梳理，
    覆盖正常登录、错误密码、账号锁定、验证码验证、第三方登录等场景，
    包括功能测试、安全测试和异常场景测试，
    输出为标准测试用例表格格式（含前置条件、步骤、预期结果）"

"分析支付接口文档，设计完整的接口测试用例，
    需要先进行接口��析（参数、响应、业务流程），
    然后设计覆盖支付成功、失败、超时、重复支付等场景的测试用例，
    确保覆盖所有边界条件和异常情况"

CODE_GENERATE:
"使用Python实现一个线程安全的LRU缓存类，支持get和put操作，
    要求O(1)时间复杂度，容量可配置（默认128），支持自定义淘汰策略，
    使用类型注解，遵循PEP8规范，包含完整的docstring文档和单元测试，
    测试覆盖率要求80%以上"

"基于pytest + requests + allure框架编写接口自动化测试代码，
    根据已有的测试用例文档实现完整的测试脚本，
    包含测试数据准备、接口调用、断言验证、报告生成，
    代码结构保持简单直接，不需要多环境配置和复杂日志系统，
    专注于测试逻辑的核心实现和测试结果的清晰展示"

**上下文关联示例**：

前序任务关联示例：
"基于之前任务生成的config.json配置文件，实现数据库连接管理模块，
    需要读取config.json中的数据库配置信息，保持与已有日志模块的接口一致性，
    确保与之前定义的错误处理规范兼容"

后续任务适配示例：
"生成用户管理API接口代码，考虑到后续任务需要实现前端调用和单元测试，
    确保API接口符合RESTful规范，返回格式统一为JSON，
    预留权限验证中间件接口，代码结构便于后续扩展CRUD操作"

**不好的描述**：
"搜索一下AI" （目标不明确，范围太广，缺少输出要求）
"分析这个文档" （没说明分析目标和关注点）
"生成测试用例" （缺少功能说明和覆盖要求）
"写个缓存" （缺少技术要求和实现细节）

**特别提醒 - 测试用例相关任务的正确选择**：
❌ 错误：选择CONTENT_ANALYSIS来"分析接口文档并生成测试用例"
✅ 正确：选择TEST_CASE_GENERATE来"分析接口文档并生成测试用例"

❌ 错误：选择CODE_GENERATE来"设计API测试场景"
✅ 正确：选择TEST_CASE_GENERATE来"设计API测试场景"

❌ 错误：选择CONTENT_ANALYSIS来"接口测试用例设计"
✅ 正确：选择TEST_CASE_GENERATE来"接口测试用例设计"

【发散思路】
可以从以下角度丰富任务描述：
- 为什么要做：任务的业务背景、目的或价值
- 怎么做：建议的方法、步骤或技术路线
- 做到什么程度：成功的标准和验收条件
- 注意什么：需要规避的风险、易错点或特殊情况
- 参考什么：相关文档、示例、最佳实践或类似案例
- 用在哪里：输出结果的使用场景和受众
- 与前后任务的关系：如何承接前序任务成果，如何为后续任务做准备
"""

class SubAgentExecute(BaseTool):
    """该工具作为任务分发中心，能够根据任务的性质、复杂度和领域特征，
    自动匹配并调用最适合的专业子代理来完成工作。支持各类任务场景，
    包括但不限于数据处理、内容生成、分析计算、自动化操作等。"""
    name: str = "sub_agent_run"
    description: str = _SUB_AGENT_EXECUTE_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": _AGENT_NAME_DESCRIPTION,
                "enum": AGENT_LIST,
            },
            "task": {
                "type": "string",
                "description": _AGENT_TASK_DESCRIPTION,
            },
            # "context": {
            #     "type": "string",
            #     "description": "任务执行的上下文信息，可选参数，提供额外的背景信息帮助子代理更好地理解任务",
            #     "default": "",
            # },
        },
        "required": ["agent_name", "task"],
    }
    agent_pools: Dict[str, Any] = {}
    
    llm_config: Optional[LLMConfig] = Field(default=None, description="LLM配置")
    memory: Optional[BaseMemory] = Field(default_factory=BaseMemory, description="记忆模块")
    artifact_manager: Optional[ArtifactManager] = Field(default=None, description="Artifact管理器")

    async def execute(self, agent_name: str, task: str, context: str = ""):
        """
        执行子代理任务
        
        Args:
            agent_name: 子代理名称
            task: 具体任务描述
            context: 任务上下文信息
            **kwargs: 其他参数
            
        Returns:
            子代理执行结果
            
        Raises:
            ToolError: 当代理不存在或执行失败时抛出
        """        
        # try:
        # 验证代理名称是否有效
        if agent_name not in AGENT_LIST:
            valid_agents = ", ".join(AGENT_LIST)
            raise ToolError(f"无效的代理名称: {agent_name}。可用代理: {valid_agents}")
        
        # 检查代理池中是否存在该代理
        if agent_name not in self.agent_pools:
            raise ToolError(f"代理 '{agent_name}' 未在代理池中找到。请确保该代理已正确初始化。")
        
        agent_class = self.agent_pools[agent_name]
        agent = agent_class(
            llm_config=self.llm_config,
            memory=self.memory,
            artifact_manager=self.artifact_manager
        )
        
        # 构建完整的任务描述
        full_task = task
        if context:
            full_task = f"上下文: {context}\n\n任务: {task}"
        
        logger.info(f"开始执行子代理任务 - 代理: {agent_name}, 任务: {task[:100]}...")
        
        # 执行子代理任务
        result = ""
        async for chunk in agent.run(full_task):
            result += chunk
            yield chunk
        
        logger.info(f"子代理任务执行完成 - 代理: {agent_name}")
        # return result
        
        # except Exception as e:
        #     error_msg = f"子代理执行失败 - 代理: {agent_name}, 错误: {str(e)}"
        #     logger.error(error_msg)
        #     raise ToolError(error_msg)