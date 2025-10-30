"""
LLM工具调用测试
"""
import asyncio
import os
import sys

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from llm.llm import (
    LLMConfig, OpenAILLM, MessageRole,
    create_text_message,
    create_tool_message, create_assistant_message_with_tool_calls
)

from backend.tools.base import ToolFunction
from dotenv import load_dotenv

load_dotenv()

async def test_tool_calling():
    """测试工具调用功能"""
    print("=== LLM工具调用测试 ===")
    
    try:
        # 定义计算器工具
        calculator_tool = ToolFunction(
            name="calculator",
            description="执行基本数学计算",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要计算的数学表达式，例如: '2 + 3 * 4'"
                    }
                },
                "required": ["expression"]
            }
        )
        
        # 定义获取时间工具
        get_time_tool = ToolFunction(
            name="get_current_time",
            description="获取当前时间",
            parameters={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "时区，例如: 'Asia/Shanghai'",
                        "default": "UTC"
                    }
                }
            }
        )
        
        # 创建配置
        config = LLMConfig(
            model_name="MaaS_Sonnet_4",
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE"),
            stream=True,
            tools=[calculator_tool, get_time_tool]
        )
        
        # 创建LLM实例
        llm = OpenAILLM(config)
        
        # 测试1: 基础工具调用
        print("\n1. 测试计算器工具调用")
        user_msg = create_text_message(
            MessageRole.USER, 
            "请帮我计算 15 + 27 * 3 的结果, 调用工具进行计算"
        )
        
        print(f"用户: {user_msg.content}")
        print("AI: ", end="", flush=True)
        
        tool_calls = []
        content_parts = []
        
        async for chunk in await llm.generate([user_msg]):
            if chunk.content:
                content_parts.append(chunk.content)
                print(chunk.content, end="", flush=True)
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
            # if chunk.is_complete:
            #     break
        
        print()  # 换行
        
        # 处理工具调用
        if tool_calls:
            print("\n检测到工具调用:")
            for tool_call in tool_calls:
                print(f"  工具: {tool_call.function['name']}")
                print(f"  参数: {tool_call.function['arguments']}")
                
                # 模拟工具执行
                result = simulate_tool_execution(tool_call)
                print(f"  结果: {result}")
                
                # 创建完整的对话历史
                assistant_msg = create_assistant_message_with_tool_calls(
                    "".join(content_parts), tool_calls
                )
                tool_response = create_tool_message(tool_call.id, result)
                
                conversation = [user_msg, assistant_msg, tool_response]
                
                print("AI最终回复: ", end="", flush=True)
                async for final_chunk in await llm.generate(conversation):
                    if final_chunk.content:
                        print(final_chunk.content, end="", flush=True)
                    if final_chunk.is_complete:
                        print()
                        break
        
        # 测试2: 时间工具调用
        print("\n2. 测试时间工具调用")
        time_msg = create_text_message(
            MessageRole.USER,
            "现在是几点？请告诉我当前的时间，调用工具计算"
        )
        
        print(f"用户: {time_msg.content}")
        print("AI: ", end="", flush=True)
        
        tool_calls = []
        content_parts = []
        
        async for chunk in await llm.generate([time_msg]):
            if chunk.content:
                content_parts.append(chunk.content)
                print(chunk.content, end="", flush=True)
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
        
        print()
        
        if tool_calls:
            print("\n检测到工具调用:")
            for tool_call in tool_calls:
                print(f"  工具: {tool_call.function['name']}")
                print(f"  参数: {tool_call.function['arguments']}")
                
                result = simulate_tool_execution(tool_call)
                print(f"  结果: {result}")
                
                assistant_msg = create_assistant_message_with_tool_calls(
                    "".join(content_parts), tool_calls
                )
                tool_response = create_tool_message(tool_call.id, result)
                
                conversation = [time_msg, assistant_msg, tool_response]
                
                print("AI最终回复: ", end="", flush=True)
                async for final_chunk in await llm.generate(conversation):
                    if final_chunk.content:
                        print(final_chunk.content, end="", flush=True)
                    if final_chunk.is_complete:
                        print()
                        break
        
        print("\n=== 测试完成 ===")
        
    except Exception as e:
        print(f"测试出错: {e}")
        import traceback
        traceback.print_exc()


def simulate_tool_execution(tool_call):
    """模拟工具执行"""
    import json
    from datetime import datetime
    
    function_name = tool_call.function['name']
    arguments = json.loads(tool_call.function['arguments'])
    
    if function_name == "calculator":
        expression = arguments.get('expression', '')
        try:
            # 简单的计算器实现（实际应用中应该使用更安全的方法）
            # 只允许基本的数学运算
            allowed_chars = set('0123456789+-*/(). ')
            if all(c in allowed_chars for c in expression):
                result = eval(expression)
                return f"计算结果: {expression} = {result}"
            else:
                return "错误: 包含不支持的字符"
        except Exception as e:
            return f"计算错误: {str(e)}"
    
    elif function_name == "get_current_time":
        timezone = arguments.get('timezone', 'UTC')
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"当前时间 ({timezone}): {current_time}"
    
    else:
        return f"未知工具: {function_name}"


if __name__ == "__main__":
    asyncio.run(test_tool_calling())