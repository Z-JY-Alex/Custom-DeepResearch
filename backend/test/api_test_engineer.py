import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.agent.api_test_engineer import ApiTestEngineerAgent
from backend.llm.base import LLMConfig


llm_config = LLMConfig(
    api_key="amep3rwbqWIpFoOnKpZw",
    base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
    max_tokens=64000
)


async def main(task, api_docs):
    client = ApiTestEngineerAgent(llm_config=llm_config)
    
    print(f"开始执行分析任务: {task}")
    
    async for chunk in client.run(task, api_docs=api_docs):
        print(chunk, end='')


if __name__ == "__main__":
    import asyncio
    
    with open("/data/zhujingyuan/deepresearch/api_docs_test.md", "r") as f:
        api_docs = f.read()
    task_name = "请完成`我的数字人列表（我的和公共的区分返回）`接口的自动化测试代码编写"

    asyncio.run(main(task_name, api_docs))