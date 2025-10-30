import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
# tools/artifact_write.py
from typing import Dict, Any, Optional, List
from backend.tools.base import BaseTool, ToolError, ToolCallResult
from backend.artifacts.manager import ArtifactManager
from backend.artifacts.schema import ArtifactType


_ARTIFACT_DESCRIPTION = """
结果信息提炼员工具 - 将 Agent 的执行结果转化为完整、结构化的"黑板摘要"，供其他 Agent 观察、引用和决策使用。

<核心职责>
作为信息中枢，你需要将执行结果转化为其他 Agent 可以直接使用的标准化摘要信息，使其他 Agent 能够准确理解、定位和使用这些结果。
</核心职责>

<严格遵守的规则>
1. 总体描述原则（必需）
   - 每个摘要必须以总体描述开头
   - 总体描述用1-3句话概括任务的核心成果
   - 说明"完成了什么"、"解决了什么问题"或"产出了什么"
   - 为后续的详细信息提供上下文

2. 信息完整性原则
   - 保留所有与任务结果相关的关键信息，不得遗漏
   - 对于复杂任务（如代码生成、多文件创建），必须详细记录每个输出物
   - 每个文件/组件都要说明其作用、功能和位置
   - 如果有依赖关系或调用关系，必须明确说明

3. 结构化表达原则
   - 使用"总体描述 + 详细列表"的两层结构
   - 复杂结果需要分层描述（总述 → 分类 → 详细列表）
   - 文件类结果必须包含：文件路径、文件作用、关键内容说明

4. 信息精炼原则
   - 剔除执行过程中的日志、调试信息、错误重试等过程性描述
   - 剔除冗余的客套话和无关说明
   - 专注于"做了什么"和"结果是什么"，而非"怎么做的"

5. 可引用性原则
   - 其他 Agent 应该能够直接根据摘要定位和使用结果
   - 文件路径必须准确完整（绝对路径或相对路径）
   - 如果有多个产出物，需要清晰的索引或编号

6. 格式要求
   - 输出纯文本摘要，不要添加额外的元说明
   - 不要使用"摘要如下："、"总结："等开头
   - 直接给出结构化的结果描述

</严格遵守的规则>

<标准输出结构>
所有摘要必须遵循以下结构：
```
【总体描述】
用1-3句话概括核心成果

【详细信息】
根据任务类型组织的具体内容
```
</标准输出结构>

<输出示例>
单文件场景示例：
```
【总体描述】
完成了用户认证模块的核心实现，提供了完整的登录、注册和Token验证功能。

【详细信息】
生成文件：
- 文件位置：./src/auth/user_auth.py
- 主要功能：实现用户登录、注册、密码验证和Token生成
- 关键组件：UserAuth类、login()方法、register()方法、validate_token()方法
- 依赖项：需要bcrypt库进行密码加密，需要jwt库生成Token
```

多文件场景示例：
```
【总体描述】
完成了用户管理模块的完整开发，包含业务逻辑、API接口、数据模型和单元测试，形成了可独立运行的功能模块。

【详细信息】
生成的文件结构：

1. 核心业务逻辑层
   - ./src/user/user_service.py：用户CRUD操作服务类，提供创建、查询、更新、删除用户的业务方法
   - ./src/user/user_model.py：用户数据模型定义，包含User类和数据库ORM映射

2. API接口层
   - ./src/api/user_api.py：RESTful API端点实现，暴露/users路径下的GET、POST、PUT、DELETE接口

3. 工具类
   - ./src/utils/validator.py：用户输入验证工具，验证邮箱格式、密码强度、手机号格式等

4. 测试文件
   - ./tests/test_user_service.py：用户服务的单元测试，包含18个测试用例，覆盖率85%

技术依赖：
- 数据库：SQLAlchemy ORM
- Web框架：Flask-RESTful
- 验证库：email-validator

调用关系：
user_api.py → user_service.py → user_model.py
```
</输出示例>

<字数说明>
不限制摘要长度，确保信息完整性优先于简洁性。简单任务可以简短（50-100字），复杂任务需要详尽描述（300-500字或更多）。
</字数说明>
"""


class ArtifactWriteTool(BaseTool):
    """
    结果信息提炼员工具
    """
    
    name: str = "artifact_write"
    description: str = _ARTIFACT_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            # "content": {
            #     "type": "string",
            #     "description": "要写入artifact的内容",
            #     "default": ""
            # },
            "artifact_type": {
                "type": "string",
                "enum": ["text", "file", "image", "audio", "video", "other"],
                "description": """工件类型，用于标识结果的形态：
                - text: 纯文本结果（分析报告、总结、说明等）
                - file: 生成的文件（代码文件、文档、配置文件等）
                - image: 图片类结果（图表、设计稿等）
                - audio: 音频类结果
                - video: 视频类结果
                - other: 其他类型
                
                选择建议：
                - 如果任务生成了代码/配置文件，选择 file
                - 如果任务产出是文本分析/总结，选择 text
                - 如果生成了多种类型，选择最主要的类型
                """,
                "default": "text"
            },
            "name": {
                "type": "string",
                "description": """工件名称，用于快速识别和索引此结果。
                
                命名建议：
                - 使用描述性名称，体现结果的核心内容
                - 对于代码：可使用"模块名_功能描述"，如"user_auth_module"
                - 对于分析：可使用"文档名_分析类型"，如"PRD_v2.3_需求分析"
                - 对于测试：可使用"功能名_测试用例"，如"login_test_cases"
                - 避免使用过于通用的名称如"result"、"output"
                
                示例：
                - "user_management_api_implementation"
                - "sales_data_q4_analysis"
                - "payment_module_test_suite"
                """,
                "default": None
            },
            "summary": {
                "type": "string",
                "description": """结果摘要，必须详细、完整、结构化。
                
                【必须包含的信息】
                
                1. 对于代码/文件生成任务：
                   - 所有生成文件的完整路径（绝对路径或相对路径）
                   - 每个文件的功能说明和关键组件
                   - 文件之间的依赖关系和调用关系
                   - 需要的外部依赖（库、框架、环境）
                   - 如有配置文件，说明配置项的作用
                
                2. 对于文档分析任务：
                   - 核心发现和关键结论
                   - 提取的关键信息（功能点、需求、指标等）
                   - 识别的问题、风险或矛盾点
                   - 重要的依赖关系或流程
                
                3. 对于搜索任务：
                   - 关键信息及其来源
                   - 核心结论和发现
                   - 不同来源的观点对比（如有）
                   - 时间、地点、人物等关键要素
                   - 信息的可信度评估
                
                4. 对于测试用例生成任务：
                   - 测试用例文件的位置
                   - 覆盖的测试场景类型和总数
                   - 不同优先级的用例分布
                   - 特殊/复杂场景的说明
                   - 测试数据的准备要求
                
                【格式要求】
                - 使用清晰的结构（分点、分段、编号）
                - 复杂结果先总述后详细列举
                - 文件路径使用准确的格式
                - 不要包含过程性描述（如"首先...然后...最后..."）
                - 不要包含元说明（如"摘要如下："）
                
                【长度说明】
                - 简单任务：50-100字即可
                - 中等复杂度：200-300字
                - 复杂任务（多文件、多组件）：300-500字或更多
                - 原则：确保信息完整，不要为了简洁而遗漏关键信息
                
                【反例】❌
                "生成了登录功能的代码"
                → 缺少文件路径、功能细节、依赖关系
                
                【正例】✅
                "生成了用户登录功能的完整实现，包含3个文件：
                1. ./src/auth/login_service.py - 登录业务逻辑，包含验证、Token生成
                2. ./src/api/login_api.py - RESTful登录接口，暴露/api/login端点
                3. ./tests/test_login.py - 单元测试，覆盖正常登录、错误密码等8个场景
                依赖：需要安装bcrypt和PyJWT库，需要配置JWT_SECRET环境变量"
                """,
                "default": None
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": """工件标签列表，用于分类和快速检索（可选）。
                
                建议的标签类型：
                - 任务类型：如"代码生成"、"文档分析"、"测试用例"、"搜索结果"
                - 技术栈：如"Python"、"React"、"MySQL"
                - 模块名称：如"用户管理"、"支付系统"、"数据分析"
                - 优先级：如"P0"、"P1"、"紧急"
                - 状态：如"待审核"、"已完成"、"需补充"
                
                示例：["Python", "用户认证", "代码生成", "P0"]
                """,
                "default": []
            },
            "content_location": {
                "type": "string",
                "description": """主要内容的存储位置（可选）。
                
                【使用场景】
                - 当生成了文件时，这里可以填写主文件的路径
                - 当有多个文件时，可以填写主目录或入口文件
                - 当内容存储在特定位置时，提供该位置的路径
                
                【路径要求】
                - 使用绝对路径或当前工程下的相对路径
                - 相对路径以项目根目录为基准
                - 确保路径的准确性和可访问性
                
                【注意】
                - 如果有多个文件，详细的路径列表应该写在 summary 中
                - 此字段仅作为快速定位的辅助信息
                - 可以为空，不影响 summary 的完整性
                
                示例：
                - ".output/project/src/user/user_service.py"（单文件）
                - ".output/project/src/auth/"（多文件目录）
                - "/home/project/output/report.md"（绝对路径）
                """,
                "default": None
            }
        },
        "required": ["name", "summary"]
    }
    artifact_manager: Optional[ArtifactManager] = None
    
    def __init__(self, artifact_manager: Optional[ArtifactManager] = None, **kwargs):
        """
        初始化工件写入工具
        
        Args:
            artifact_manager: ArtifactManager实例
        """
        super().__init__(**kwargs)
        self.artifact_manager = artifact_manager or ArtifactManager()
        
    async def execute(
        self,
        *,
        artifact_type: str = "text",
        name: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
        content_location: Optional[str] = None,
        **kwargs
    ) -> ToolCallResult:
        """
        执行工件写入操作
        
        Args:
            content: 要写入的内容
            artifact_type: 工件类型
            name: 工件名称
            summary: 工件摘要
            tags: 标签列表
            content_location: 内容位置
        """
        try:
            # 转换工件类型
            try:
                artifact_type_enum = ArtifactType(artifact_type.lower())
            except ValueError:
                raise ToolError(f"不支持的工件类型: {artifact_type}。支持的类型: text, file, image, audio, video, other")
            
            # 准备元数据
            metadata = {}
            if name:
                metadata["name"] = name
            metadata["created_by"] = "artifact_write_tool"
            
            # 创建工件
            artifact = await self.artifact_manager.create_artifact(
                content="",
                summary=summary,
                artifact_type=artifact_type_enum,
                metadata=metadata,
                tags=tags or [],
                file_path=content_location
            )
            
            # 构建返回结果
            result_info = {
                "artifact_id": artifact.artifact_id,
                "artifact_type": artifact.artifact_type.value,
                "name": name or artifact.artifact_id,
                "summary": summary,
                "content_length": 0,
                "tags": tags or [],
                "content_location": content_location
            }
            
            success_msg = f"工件创建成功: {artifact.artifact_id}"
            if name:
                success_msg += f" (名称: {name})"
            if content_location:
                success_msg += f"\n内容位置: {content_location}"
            
            return ToolCallResult(
                tool_call_id="artifact_write",
                result=success_msg,
                output=result_info
            )
            
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"工件写入失败: {str(e)}")