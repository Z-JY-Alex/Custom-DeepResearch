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


async def simulate_user_answer(interaction_manager: InteractionManager, interaction_id: str, answer: str, delay: float = 1.0):
    """模拟用户延迟回答"""
    await asyncio.sleep(delay)
    success = await interaction_manager.submit_answer(interaction_id, answer)
    logger.info(f"🤔 模拟用户回答: {answer}, 成功: {success}")
    return success


async def capture_interaction_and_answer(chunk: str, interaction_manager: InteractionManager, answer_map: dict = None):
    """
    捕获工具发送的交互事件并自动回答
    
    Args:
        chunk: 工具输出的chunk
        interaction_manager: 交互管理器
        answer_map: 回答映射 {question_keyword: answer}，用于自动回答不同类型的问题
    """
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
            question_type = event_data.get("question_type", "text")
            
            if interaction_id:
                # 根据问题内容自动选择回答
                answer = None
                if answer_map:
                    for keyword, ans in answer_map.items():
                        if keyword.lower() in question.lower():
                            answer = ans
                            break
                
                # 如果没有匹配的回答，使用默认回答
                if answer is None:
                    if question_type == "choice":
                        options = event_data.get("options", [])
                        answer = options[0] if options else "选项1"
                    elif question_type == "confirm":
                        answer = "是"
                    else:
                        answer = "默认回答"
                
                # 异步提交回答（延迟1秒模拟用户思考时间）
                logger.info(f"📝 检测到问题: {question}")
                logger.info(f"💭 自动回答: {answer}")
                asyncio.create_task(
                    simulate_user_answer(interaction_manager, interaction_id, answer, delay=1.0)
                )
                return interaction_id, question, answer
                
        except Exception as e:
            logger.error(f"解析交互事件失败: {e}, chunk: {chunk[:100]}")
    
    return None, None, None


async def test_llm_with_user_interaction():
    """测试大模型是否能正确调用用户交互工具"""
    logger.info("=" * 80)
    logger.info("测试：大模型调用用户交互工具")
    logger.info("=" * 80)
    
    # 创建交互管理器
    interaction_manager = InteractionManager()
    session_id = f"test_llm_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 创建用户交互工具
    user_interaction_tool = UserInteractionTool(
        interaction_manager=interaction_manager,
        session_id=session_id
    )
    
    # 创建LLM配置，包含用户交互工具
    llm_config = LLMConfig(
        api_key="amep3rwbqWIpFoOnKpZw",
        base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
        model_name="MaaS_Sonnet_4",
        max_tokens=64000,
        stream=True,
        tools=[user_interaction_tool]
    ) 
    
    llm = OpenAILLM(llm_config)
    
    # 定义一个需要询问用户的任务
    user_msg = Message(
        role=MessageRole.USER,
        content="""我需要创建一个新的项目，但我还不确定以下信息：
1. 项目名称
2. 使用的编程语言（Python、JavaScript、Java、Go）
3. 是否需要使用数据库

请你帮我询问用户这些信息，然后根据用户的回答创建一个项目。""",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        metadata={"current_round": 0}
    )
    
    logger.info(f"📤 用户消息: {user_msg.content}")
    logger.info("-" * 80)
    
    # 定义自动回答映射（根据问题关键词自动回答）
    answer_map = {
        "项目名称": "MyTestProject",
        "编程语言": "Python",
        "数据库": "是",
        "language": "Python",
        "database": "是"
    }
    
    conversation = [user_msg]
    tool_calls = []
    current_round = 0
    max_rounds = 10
    
    while current_round < max_rounds:
        current_round += 1
        logger.info(f"\n🔄 第 {current_round} 轮对话")
        logger.info("-" * 80)
        
        cur_content = ""
        tool_calls = []
        
        # LLM生成响应
        async for chunk in await llm.generate(conversation, tools=[user_interaction_tool]):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                cur_content += chunk.content
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
        
        print()  # 换行
        
        # 处理工具调用（在收集完所有chunk后处理）
        if tool_calls:
            print("\n检测到工具调用:")
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
                
                logger.info(f"  工具: {function_name}")
                logger.info(f"  参数: {arguments}")
                print(f"\n\n<TOOL_CALL> {function_name} </TOOL_CALL>")
                print(f"<TOOL_ARGS> {arguments} </TOOL_ARGS>")
                print("<TOOL_RESULT>")
                
                # 执行用户交互工具
                if function_name == "ask_user":
                    tool_result_content = ""
                    async for tool_result in user_interaction_tool(**arguments):
                        print(tool_result, end="", flush=True)
                        tool_result_content += tool_result
                        
                        # 捕获交互事件并自动回答
                        interaction_id, question, answer = await capture_interaction_and_answer(
                            tool_result, interaction_manager, answer_map
                        )
                    
                    # 等待用户回答被处理（工具会等待）
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
                    print(tool_result_content)
                else:
                    logger.warning(f"未知工具: {function_name}")
            
            tool_calls = []
            cur_content = ""
            # 等待一下，确保异步任务完成
            await asyncio.sleep(0.5)
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
        else:
            # 没有工具调用，可能对话结束
            logger.info("\n✅ 对话完成，没有更多工具调用")
            break
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ 测试完成！")
    logger.info(f"📊 总轮次: {current_round}")
    logger.info(f"📝 对话历史长度: {len(conversation)}")
    
    # 显示交互统计
    stats = interaction_manager.get_stats()
    logger.info(f"📈 交互统计: {stats}")


async def test_llm_choice_question():
    """测试大模型调用选择题类型的用户交互"""
    logger.info("\n" + "=" * 80)
    logger.info("测试：大模型调用选择题类型的用户交互")
    logger.info("=" * 80)
    
    interaction_manager = InteractionManager()
    session_id = f"test_choice_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    user_interaction_tool = UserInteractionTool(
        interaction_manager=interaction_manager,
        session_id=session_id
    )
    
    llm_config = LLMConfig(
        api_key="amep3rwbqWIpFoOnKpZw",
        base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
        model_name="MaaS_Sonnet_4",
        max_tokens=64000,
        stream=True,
        tools=[user_interaction_tool]
    )
    
    llm = OpenAILLM(llm_config)
    
    user_msg = Message(
        role=MessageRole.USER,
        content="我需要选择一个后端框架，请询问用户希望使用哪个框架。可选项：Django、Flask、FastAPI、Spring Boot",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        metadata={"current_round": 0}
    )
    
    logger.info(f"📤 用户消息: {user_msg.content}")
    logger.info("-" * 80)
    
    answer_map = {
        "框架": "FastAPI",
        "framework": "FastAPI"
    }
    
    conversation = [user_msg]
    current_round = 0
    
    while current_round < 5:
        current_round += 1
        tool_calls = []
        cur_content = ""
        
        async for chunk in await llm.generate(conversation, tools=[user_interaction_tool]):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                cur_content += chunk.content
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
        
        if cur_content:
            conversation.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=cur_content,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    metadata={"current_round": current_round}
                )
            )
        
        if tool_calls:
            print("\n\n🔧 工具调用:")
            conversation.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content="",
                    tool_calls=tool_calls,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    metadata={"current_round": current_round}
                )
            )
            
            for tool_call in tool_calls:
                if tool_call.function['name'] == "ask_user":
                    arguments = json.loads(tool_call.function['arguments'])
                    print(f"\n调用工具: ask_user")
                    print(f"参数: {arguments}\n")
                    
                    tool_result_content = ""
                    async for tool_result in user_interaction_tool(**arguments):
                        print(tool_result, end="", flush=True)
                        tool_result_content += tool_result
                        await capture_interaction_and_answer(tool_result, interaction_manager, answer_map)
                    
                    conversation.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=tool_result_content,
                            tool_call_id=tool_call.id,
                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            metadata={"current_round": current_round}
                        )
                    )
                    await asyncio.sleep(0.5)
        else:
            break
    
    logger.info("\n✅ 选择题测试完成")


async def test_llm_confirm_question():
    """测试大模型调用确认题类型的用户交互"""
    logger.info("\n" + "=" * 80)
    logger.info("测试：大模型调用确认题类型的用户交互")
    logger.info("=" * 80)
    
    interaction_manager = InteractionManager()
    session_id = f"test_confirm_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    user_interaction_tool = UserInteractionTool(
        interaction_manager=interaction_manager,
        session_id=session_id
    )
    
    llm_config = LLMConfig(
        api_key="amep3rwbqWIpFoOnKpZw",
        base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
        model_name="MaaS_Sonnet_4",
        max_tokens=64000,
        stream=True,
        tools=[user_interaction_tool]
    )
    
    llm = OpenAILLM(llm_config)
    
    user_msg = Message(
        role=MessageRole.USER,
        content="我准备删除一个重要的文件，请先向用户确认是否真的要删除。",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        metadata={"current_round": 0}
    )
    
    logger.info(f"📤 用户消息: {user_msg.content}")
    logger.info("-" * 80)
    
    answer_map = {
        "删除": "是",
        "delete": "是"
    }
    
    conversation = [user_msg]
    current_round = 0
    
    while current_round < 5:
        current_round += 1
        tool_calls = []
        cur_content = ""
        
        async for chunk in await llm.generate(conversation, tools=[user_interaction_tool]):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                cur_content += chunk.content
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
        
        if cur_content:
            conversation.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=cur_content,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    metadata={"current_round": current_round}
                )
            )
        
        if tool_calls:
            print("\n\n🔧 工具调用:")
            conversation.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content="",
                    tool_calls=tool_calls,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    metadata={"current_round": current_round}
                )
            )
            
            for tool_call in tool_calls:
                if tool_call.function['name'] == "ask_user":
                    arguments = json.loads(tool_call.function['arguments'])
                    print(f"\n调用工具: ask_user")
                    print(f"参数: {arguments}\n")
                    
                    tool_result_content = ""
                    async for tool_result in user_interaction_tool(**arguments):
                        print(tool_result, end="", flush=True)
                        tool_result_content += tool_result
                        await capture_interaction_and_answer(tool_result, interaction_manager, answer_map)
                    
                    conversation.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=tool_result_content,
                            tool_call_id=tool_call.id,
                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            metadata={"current_round": current_round}
                        )
                    )
                    await asyncio.sleep(0.5)
        else:
            break
    
    logger.info("\n✅ 确认题测试完成")


async def main():
    """运行所有测试"""
    logger.info("🚀 开始测试大模型调用用户交互工具")
    logger.info("=" * 80)
    
    try:
        # 测试1: 综合测试 - LLM需要询问多个问题
        await test_llm_with_user_interaction()
        await asyncio.sleep(2)
        
        # 测试2: 选择题测试
        await test_llm_choice_question()
        await asyncio.sleep(2)
        
        # 测试3: 确认题测试
        await test_llm_confirm_question()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ 所有测试完成！")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

