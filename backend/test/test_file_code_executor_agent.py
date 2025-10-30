"""
文件代码执行代理测试
"""
import asyncio
import os
import sys
import tempfile
import json
from pathlib import Path

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.agent.code_executor import CodeExecutorAgent
from backend.llm.base import LLMConfig
from backend.llm.llm import OpenAILLM
from loguru import logger

#
llm_config = LLMConfig(
    api_key="amep3rwbqWIpFoOnKpZw",
    base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
    max_tokens=64000
)

# 配置 loguru 同时输出到终端和日志文件
logger.remove()  # 移除默认的处理器

# 添加控制台输出（彩色格式）
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# 添加文件输出（loguru会自动创建目录）
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
logger.add(
    os.path.join(log_dir, "test_file_code_executor_agent.log"),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="INFO",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8"
)


async def main(query):
    client = CodeExecutorAgent(llm_config=llm_config)
    
    # logger.info(f"开始执行自动搜索查询: {query}")
    
    async for chunk in client.run(query):
        # 使用 logger.info 输出到终端和日志文件，同时保持原有的流式输出效果
        logger.opt(raw=True).info(chunk)


if __name__ == "__main__":
    import asyncio
    query = """
# 已完成任务列表

## 1. 任务ID: artifact_153da0294fcc4ef0ad51e48ca355418c

**名称**: 保存数字人视频详情接口_测试用例集

**路径**: output/保存数字人视频详情接口_测试用例.md

**摘要**: 【总体描述】
完成了保存数字人视频详情接口的完整测试用例集生成，涵盖功能测试、边界测试、异常测试和业务规则验证，形成了系统化的接口测试文档。

【详细信息】
生成的测试用例文件：

1. 核心测试文档
   - ./output/保存数字人视频详情接口_测试用例.md：完整的测试用例集，包含75个测试用例，覆盖20个测试场景

2. 测试场景完整覆盖
   - 场景1-2：全参路径和最小路径验证（2个用例）
   - 场景3：响应结构验证（1个用例）
   - 场景4：必填参数缺失验证（8个用例）
   - 场景5：非必填参数验证（5个用例）
   - 场景6：数组与嵌套结构验证（4个用例）
   - 场景7：类型错误验证（5个用例）
   - 场景8：空值处理验证（5个用例）
   - 场景9：枚举值验证（7个用例）
   - 场景10：格式校验验证（5个用例）
   - 场景11：数值范围边界验证（5个用例）
   - 场景12：字符串长度边界验证（5个用例）
   - 场景13：数组长度边界验证（3个用例）
   - 场景14：出参字段完整性验证（3个用例）
   - 场景15：出参字段类型验证（3个用例）
   - 场景16：出参字段值范围验证（3个用例）
   - 场景17：出参数据一致性验证（3个用例）
   - 场景18：参数依赖关系验证（3个用例）
   - 场景19：参数互斥关系验证（2个用例）
   - 场景20：业务约束规则验证（3个用例）

3. 字段覆盖完整性
   - 主体参数：9个字段全覆盖（id, name, ratio, videoId, videoUrl, firstFrame, cover, duration, segments）
   - segments参数：24个字段全覆盖（包括所有必填和非必填字段）
   - 响应字段：完整覆盖code、message、data、traceId及嵌套字段

4. 测试数据具体化
   - 所有测试数据均为具体可执行的JSON格式
   - 涵盖有效值、边界值、异常值的完整测试
   - 包含中文、英文、特殊字符、emoji等多种字符类型
   - 提供完整的Cookie认证信息和URL配置

5. 业务规则验证
   - id<10000的业务约束验证
   - segments数组非空验证
   - JSON字段格式严格验证
   - 权限认证机制验证
   - 参数依赖关系验证（type=2时音频字段依赖）
   - 数据一致性验证（digitalVideoId与主体id一致性）

技术特点：
- 严格按照20个场景顺序执行，确保测试覆盖完整性
- 基于文档信息设计，避免过度推测和延伸
- 使用通用边界规则处理文档未明确的边界情况
- 测试用例可直接执行，包含完整的前置条件和期望结果
- 支持不同优先级的测试执行策略

输出格式：
- 标准Markdown格式，结构清晰
- 表格化测试用例，便于执行和维护
- 完整的测试总结和执行建议
- 环境要求和数据准备说明

---

当前任务:
搭建数字人视频详情保存接口的自动化测试环境和配置。

**技术栈要求：**
- pytest：测试框架
- requests：HTTP请求库
- allure-pytest：测试报告生成
- pytest-html：备用HTML报告

**项目结构要求：**
创建完整的测试项目结构，包括：
```
digital_human_test/
├── requirements.txt          # 依赖包
├── pytest.ini              # pytest配置
├── conftest.py              # 测试配置和fixture
├── config/
│   ├── __init__.py
│   ├── config.py            # 测试配置类
│   └── test_data.py         # 测试数据管理
├── utils/
│   ├── __init__.py
│   ├── api_client.py        # API客户端封装
│   ├── logger.py            # 日志工具
│   └── helpers.py           # 辅助工具函数
├── tests/
│   ├── __init__.py
│   └── test_save_digital_video.py  # 主测试文件
├── reports/                 # 测试报告目录
└── logs/                    # 日志目录
```

**配置内容要求：**
1. **requirements.txt**：包含所有必需的依赖包及版本
2. **pytest.ini**：pytest运行配置，包括allure集成
3. **conftest.py**：全局fixture和测试配置
4. **config.py**：环境配置管理（URL、认证信息等）
5. **api_client.py**：封装HTTP请求，包含认证处理
6. **logger.py**：日志配置和管理
7. **test_data.py**：测试数据管理类

**特殊要求：**
1. 支持多环境配置（开发、测试、生产）
2. 集成Cookie认证机制
3. 支持请求/响应日志记录
4. 支持测试数据参数化
5. 集成allure报告生成
6. 异常处理和重试机制
7. 支持并发测试执行

**认证信息：**
- 当前Cookie：已提供的有效Cookie字符串
- 失败Cookie：已提供的失效Cookie字符串
- BaseURL：https://digital-human-service.zhihuishu.com/

**输出要求：**
生成完整的项目文件，每个文件都要包含详细的注释和使用说明。确保项目结构清晰，代码规范，便于维护和扩展。
    """
    asyncio.run(main(query))
