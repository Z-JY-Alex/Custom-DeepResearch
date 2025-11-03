import os
import sys
from loguru import logger

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.agent.planner_ai_test import PlanAgent
from backend.agent.search import SearchAgent
from backend.agent.content_analyzer import ContentAnalyzerAgent
from backend.agent.generate_test_cases import TestCasesGeneratorAgent
from backend.agent.code_executor import CodeExecutorAgent
from backend.llm.base import LLMConfig
from backend.memory.base import BaseMemory
from backend.artifacts.manager import ArtifactManager


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
    os.path.join(log_dir, "test_auto_search_agent_new.log"),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="INFO",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8"
)


async def main(query):
    memory = BaseMemory(compression_llm_config=llm_config)
    artifact_manager = ArtifactManager()

    agent_maps = {
        "WEB_SEARCH": SearchAgent,
        "CONTENT_ANALYSIS": ContentAnalyzerAgent,
        "TEST_CASE_GENERATE": TestCasesGeneratorAgent,
        "CODE_GENERATE": CodeExecutorAgent
    }

    client = PlanAgent(llm_config=llm_config, agent_maps=agent_maps, memory=memory, artifact_manager=artifact_manager)
    
    logger.info(f"开始执行自动搜索查询: {str(query)[:100]}...")
    
    async for chunk in client.run(query):
        # 使用 logger.info 输出到终端和日志文件，同时保持原有的流式输出效果
        logger.opt(raw=True).info(chunk)


if __name__ == "__main__":
    import asyncio
    # 使用相对于项目根目录的路径
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    api_docs_path = os.path.join(project_root, "api_docs_test.md")
    with open(api_docs_path, "r", encoding="utf-8") as f:
        api_docs = f.read()
    asyncio.run(main(f"{api_docs}"))
    # asyncio.run(main("制定一个计划，先计算1+1的结果，然后在加上2， 并将结果保存为result.md文件，在读取文件内容"))
