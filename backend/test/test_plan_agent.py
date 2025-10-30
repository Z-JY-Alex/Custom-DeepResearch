import os
import sys
from loguru import logger

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.agent.planner import PlanAgent
from backend.agent.search import SearchAgent
from backend.llm.base import LLMConfig


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
    search_agent = SearchAgent(llm_config=llm_config)
    
    agent_maps = {
        "WEB_SEARCH": search_agent
    }

    client = PlanAgent(llm_config=llm_config, agent_maps=agent_maps)
    
    logger.info(f"开始执行自动搜索查询: {query}")
    
    async for chunk in client.run(query):
        # 使用 logger.info 输出到终端和日志文件，同时保持原有的流式输出效果
        logger.opt(raw=True).info(chunk)


if __name__ == "__main__":
    import asyncio
    with open("/data/zhujingyuan/deepresearch/api_docs_test.md", "r") as f:
        api_docs = f.read()
    task_name = "请完成`我的数字人列表（我的和公共的区分返回）`接口的自动化测试代码编写"
    asyncio.run(main(f"{api_docs}, task: {task_name}"))
