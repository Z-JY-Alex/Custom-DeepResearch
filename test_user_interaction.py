"""
用户交互功能测试示例
演示AI如何主动询问用户并获取回答
"""

import os
import sys
import asyncio
from loguru import logger

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.agent.planner_ai_test import PlanAgent
from backend.agent.search import SearchAgent
from backend.agent.content_analyzer import ContentAnalyzerAgent
from backend.agent.generate_test_cases import TestCasesGeneratorAgent
from backend.agent.code_executor import CodeExecutorAgent
from backend.llm.base import LLMConfig
from backend.memory.base import BaseMemory
from backend.artifacts.manager import ArtifactManager
from backend.interaction.manager import InteractionManager
from backend.prompts.plan_ai_test_with_interaction import PLANNER_INSTRUCTION_WITH_INTERACTION, PLAN_USER_PROMPT_WITH_INTERACTION
from datetime import datetime

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# LLM配置
llm_config = LLMConfig(
    api_key="amep3rwbqWIpFoOnKpZw", 
    base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
    max_tokens=64000
)

CURRENT_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
WORKDIR = os.getcwd()


class InteractiveTestAgent(PlanAgent):
    """带用户交互功能的测试Agent"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 使用带交互功能的指令
        self.instruction = PLANNER_INSTRUCTION_WITH_INTERACTION.format(
            CURRUENT_TIME=CURRENT_TIME, 
            WORKDIR=WORKDIR
        )


async def simulate_user_responses(interaction_manager: InteractionManager):
    """模拟用户回答（用于测试）"""
    await asyncio.sleep(2)  # 等待一下让AI先询问
    
    # 模拟用户回答
    test_responses = [
        ("pytest", "选择pytest作为测试框架"),
        ("https://api.example.com", "提供API基础URL"),
        ("yes", "确认删除现有文件"),
        ("API接口自动化测试", "明确测试类型")
    ]
    
    response_index = 0
    
    while response_index < len(test_responses):
        # 检查是否有待处理的交互
        if interaction_manager.pending_interactions:
            interaction_id = list(interaction_manager.pending_interactions.keys())[0]
            answer, description = test_responses[response_index]
            
            logger.info(f"🤖 模拟用户回答: {description} -> {answer}")
            await interaction_manager.submit_answer(interaction_id, answer)
            response_index += 1
            
        await asyncio.sleep(1)


async def test_user_interaction():
    """测试用户交互功能"""
    logger.info("🚀 开始测试用户交互功能")
    
    # 创建交互管理器
    interaction_manager = InteractionManager()
    
    # 创建Agent
    memory = BaseMemory()
    artifact_manager = ArtifactManager()
    
    agent_maps = {
        "WEB_SEARCH": SearchAgent,
        "CONTENT_ANALYSIS": ContentAnalyzerAgent,
        "TEST_CASE_GENERATE": TestCasesGeneratorAgent,
        "CODE_GENERATE": CodeExecutorAgent
    }
    
    agent = InteractiveTestAgent(
        llm_config=llm_config,
        agent_maps=agent_maps,
        memory=memory,
        artifact_manager=artifact_manager
    )
    
    # 启用用户交互功能
    session_id = f"test_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    agent.enable_user_interaction(interaction_manager, session_id)
    
    logger.info(f"📋 会话ID: {session_id}")
    logger.info(f"🔧 Agent工具列表: {agent.list_tools()}")
    
    # 启动模拟用户回答任务
    user_task = asyncio.create_task(simulate_user_responses(interaction_manager))
    
    # 测试查询 - 故意提供模糊信息，让AI询问用户
    test_query = "帮我做一个测试项目"
    
    logger.info(f"📝 测试查询: {test_query}")
    logger.info("=" * 80)
    
    try:
        # 执行Agent
        async for chunk in agent.run(test_query):
            print(chunk, end='', flush=True)
            
    except Exception as e:
        logger.error(f"执行失败: {e}")
    finally:
        # 取消用户模拟任务
        user_task.cancel()
        
        # 清理会话
        await interaction_manager.cleanup_session(session_id)
        
        # 显示统计信息
        stats = interaction_manager.get_stats()
        logger.info("📊 交互统计:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")


async def test_different_question_types():
    """测试不同类型的问题"""
    logger.info("🧪 测试不同类型的用户交互问题")
    
    interaction_manager = InteractionManager()
    session_id = "test_questions"
    
    # 测试选择题
    logger.info("1️⃣ 测试选择题")
    interaction_id1, future1 = await interaction_manager.create_interaction(
        session_id=session_id,
        question="请选择您喜欢的编程语言？",
        question_type="choice",
        options=["Python", "Java", "JavaScript", "Go"],
        timeout=30,
        required=True
    )
    
    # 模拟用户回答
    await asyncio.sleep(1)
    await interaction_manager.submit_answer(interaction_id1, "Python")
    answer1 = await future1
    logger.info(f"✅ 收到回答: {answer1}")
    
    # 测试确认题
    logger.info("2️⃣ 测试确认题")
    interaction_id2, future2 = await interaction_manager.create_interaction(
        session_id=session_id,
        question="是否要继续执行此操作？",
        question_type="confirm",
        timeout=30,
        required=True
    )
    
    await asyncio.sleep(1)
    await interaction_manager.submit_answer(interaction_id2, "yes")
    answer2 = await future2
    logger.info(f"✅ 收到回答: {answer2}")
    
    # 测试文本输入
    logger.info("3️⃣ 测试文本输入")
    interaction_id3, future3 = await interaction_manager.create_interaction(
        session_id=session_id,
        question="请输入您的项目名称",
        question_type="text",
        timeout=30,
        required=True
    )
    
    await asyncio.sleep(1)
    await interaction_manager.submit_answer(interaction_id3, "我的测试项目")
    answer3 = await future3
    logger.info(f"✅ 收到回答: {answer3}")
    
    # 测试超时
    logger.info("4️⃣ 测试超时情况")
    try:
        interaction_id4, future4 = await interaction_manager.create_interaction(
            session_id=session_id,
            question="这个问题会超时",
            question_type="text",
            timeout=3,  # 3秒超时
            required=True
        )
        
        answer4 = await future4  # 这里会超时
        logger.info(f"✅ 收到回答: {answer4}")
    except TimeoutError:
        logger.info("⏰ 交互超时（预期行为）")
    
    # 清理
    await interaction_manager.cleanup_session(session_id)
    logger.info("🧹 测试完成，会话已清理")


async def test_interaction_manager_only():
    """仅测试交互管理器功能（不依赖Agent）"""
    logger.info("🔧 测试交互管理器基础功能")
    
    interaction_manager = InteractionManager()
    session_id = "manager_test"
    
    # 测试创建交互
    logger.info("📝 创建交互...")
    interaction_id, future = await interaction_manager.create_interaction(
        session_id=session_id,
        question="这是一个测试问题",
        question_type="text",
        timeout=10,
        required=False
    )
    
    logger.info(f"✅ 交互已创建: {interaction_id}")
    
    # 模拟延迟后提交答案
    await asyncio.sleep(2)
    success = await interaction_manager.submit_answer(interaction_id, "测试回答")
    logger.info(f"📤 提交结果: {success}")
    
    # 等待结果
    try:
        answer = await future
        logger.info(f"✅ 收到回答: {answer}")
    except Exception as e:
        logger.error(f"❌ 获取回答失败: {e}")
    
    # 获取统计信息
    stats = interaction_manager.get_stats()
    logger.info(f"📊 统计信息: {stats}")
    
    # 清理
    await interaction_manager.cleanup_session(session_id)
    logger.info("🧹 会话已清理")


async def main():
    """主函数"""
    logger.info("🎯 用户交互功能测试开始")
    
    print("\n" + "="*80)
    print("🧪 测试1: 交互管理器基础功能")
    print("="*80)
    await test_interaction_manager_only()
    
    print("\n" + "="*80)
    print("🧪 测试2: 不同问题类型")
    print("="*80)
    await test_different_question_types()
    
    print("\n" + "="*80)
    print("🧪 测试3: Agent用户交互功能")
    print("="*80)
    await test_user_interaction()
    
    logger.info("🎉 所有测试完成！")


if __name__ == "__main__":
    asyncio.run(main())
