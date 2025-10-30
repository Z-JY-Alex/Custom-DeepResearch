import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.agent.content_analyzer import ContentAnalyzerAgent
from backend.llm.base import LLMConfig


llm_config = LLMConfig(
    api_key="amep3rwbqWIpFoOnKpZw",
    base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
    max_tokens=64000
)


async def main(task):
    client = ContentAnalyzerAgent(llm_config=llm_config)
    
    print(f"开始执行分析任务: {task}")
    
    async for chunk in client.run(task):
        print(chunk, end='')


if __name__ == "__main__":
    import asyncio
    
    # 测试任务
    test_task = """请分析以下内容并生成总结报告：

深度学习技术发展现状：
1. 在计算机视觉领域取得重大突破，图像识别准确率不断提升
2. 自然语言处理方面，大语言模型展现出强大的理解和生成能力
3. 语音识别和合成技术日趋成熟，接近人类水平

面临的挑战：
- 数据需求量大，标注成本高
- 计算资源消耗巨大
- 模型可解释性不足
- 存在偏见和安全风险

发展前景：
- 算法效率持续优化
- 硬件加速技术进步
- 跨领域应用不断拓展
- 与其他技术深度融合

请生成一份结构化的分析报告。"""

    asyncio.run(main(test_task))