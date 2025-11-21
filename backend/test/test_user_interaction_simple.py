from datetime import datetime
import os
import sys
import asyncio
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.llm.llm import OpenAILLM
from backend.llm.base import LLMConfig, Message, MessageRole
from backend.tools.user_interaction import UserInteractionTool
from backend.interaction.manager import InteractionManager
from loguru import logger


async def wait_for_user_input(interaction_manager: InteractionManager, interaction_id: str):
    """等待用户手动输入回答"""
    print("\n" + "=" * 60)
    print("⏸️  等待用户输入（请在控制台输入回答后按回车）...")
    print("=" * 60)
    
    # 在事件循环中运行阻塞的 input() 函数
    loop = asyncio.get_event_loop()
    user_answer = await loop.run_in_executor(None, lambda: input("请输入你的回答: ").strip())
    
    if user_answer:
        success = await interaction_manager.submit_answer(interaction_id, user_answer)
        if success:
            logger.info(f"✅ 用户回答已提交: {user_answer}")
        else:
            logger.error(f"❌ 提交回答失败")
    else:
        logger.warning("⚠️  未输入任何内容")


async def capture_interaction_and_wait_for_input(chunk: str, interaction_manager: InteractionManager):
    """捕获工具发送的交互事件并等待用户手动输入"""
    if "data: " in chunk and "user_question" in chunk:
        try:
            # 提取JSON部分
            json_str = chunk
            if "data: " in json_str:
                json_str = json_str.split("data: ", 1)[1]  # 只分割一次
            json_str = json_str.strip().rstrip("\n")
            event_data = json.loads(json_str)
            
            interaction_id = event_data.get("interaction_id")
            question = event_data.get("question", "")
            
            if interaction_id:
                logger.info(f"\n📝 检测到问题: {question}")
                # 启动任务等待用户输入
                asyncio.create_task(
                    wait_for_user_input(interaction_manager, interaction_id)
                )
                return interaction_id, question
                
        except Exception as e:
            logger.error(f"解析交互事件失败: {e}, chunk: {chunk[:100]}")
    
    return None, None


async def test_weather_query():
    """测试天气查询场景：用户问天气，大模型询问地点"""
    logger.info("=" * 80)
    logger.info("测试场景：询问明天的天气")
    logger.info("=" * 80)
    
    # 创建交互管理器
    interaction_manager = InteractionManager()
    session_id = f"weather_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 创建用户交互工具
    user_interaction_tool = UserInteractionTool(
        interaction_manager=interaction_manager,
        session_id=session_id
    )
    
    # 创建LLM配置
    llm_config = LLMConfig(
        api_key="amep3rwbqWIpFoOnKpZw",
        base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
        model_name="MaaS_Sonnet_4",
        max_tokens=64000,
        stream=True,
        tools=[user_interaction_tool]
    )
    
    llm = OpenAILLM(llm_config)
    
    # 用户的问题
    user_msg = Message(
        role=MessageRole.USER,
        content="hello",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        metadata={"current_round": 0}
    )
    
    logger.info(f"👤 用户问题: {user_msg.content}")
    logger.info("-" * 80)
    
    conversation = [user_msg]
    tool_calls = []
    current_round = 0
    max_rounds = 5
    
    while current_round < max_rounds:
        current_round += 1
        logger.info(f"\n🔄 第 {current_round} 轮对话")
        logger.info("-" * 80)
        
        cur_content = ""
        tool_calls = []
        
        # LLM生成响应
        print("\n🤖 AI回复: ", end="", flush=True)
        async for chunk in await llm.generate(conversation, tools=[user_interaction_tool]):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                cur_content += chunk.content
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
        
        print()  # 换行
        
        # 处理工具调用
        if tool_calls:
            print("\n🔧 检测到工具调用:")
            conversation.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=cur_content if cur_content else "",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    tool_calls=tool_calls,
                    metadata={"current_round": current_round}
                )
            )
            
            for tool_call in tool_calls:
                function_name = tool_call.function['name']
                arguments = json.loads(tool_call.function['arguments'])
                
                print(f"  工具: {function_name}")
                print(f"  参数: {arguments}")
                print(f"\n<TOOL_CALL> {function_name} </TOOL_CALL>")
                print(f"<TOOL_ARGS> {arguments} </TOOL_ARGS>")
                print("<TOOL_RESULT>")
                
                # 执行用户交互工具
                if function_name == "ask_user":
                    tool_result_content = ""
                    interaction_id = None
                    
                    async for tool_result in user_interaction_tool(**arguments):
                        print(tool_result, end="", flush=True)
                        tool_result_content += tool_result
                        
                        # 捕获交互事件并等待用户输入
                        captured_id, question = await capture_interaction_and_wait_for_input(
                            tool_result, interaction_manager
                        )
                        if captured_id:
                            interaction_id = captured_id
                    
                    # 工具会在 await future 处自动等待用户回答
                    # 所以这里不需要额外等待，工具执行完成意味着用户已经回答
                    print("\n</TOOL_RESULT>\n")
                    
                    # 添加工具结果到对话历史
                    conversation.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=tool_result_content,
                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            tool_call_id=tool_call.id,
                            metadata={"current_round": current_round}
                        )
                    )
                else:
                    logger.warning(f"未知工具: {function_name}")
            
            tool_calls = []
            cur_content = ""
        elif cur_content:
            # 如果有内容但没有工具调用，添加到对话历史
            conversation.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=cur_content,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    metadata={"current_round": current_round}
                )
            )
            logger.info("\n✅ 对话完成")
            break
        else:
            logger.info("\n✅ 对话完成，没有更多响应")
            break
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ 测试完成！")


async def main():
    """运行测试"""
    logger.info("🚀 开始测试：用户交互工具（天气查询示例）")
    
    try:
        await test_weather_query()
    except KeyboardInterrupt:
        logger.info("\n⚠️  用户中断测试")
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

