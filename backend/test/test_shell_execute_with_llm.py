from datetime import datetime
import os
import sys
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.llm.llm import OpenAILLM, LLMConfig

from backend.tools.shell_execute import ShellExecuteTool
from backend.llm.base import LLMConfig, Message, MessageRole


async def test_shell_tool():

    file_tool = ShellExecuteTool()

    llm_config = LLMConfig(
        api_key="amep3rwbqWIpFoOnKpZw",
        base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
        max_tokens=64000,
        stream=True,
        tools=[file_tool]
    )

    llm = OpenAILLM(llm_config)

    user_msg = Message(
        role=MessageRole.USER,
        content="帮我执行命令'cd output/digital_human_test && source /data/zhujingyuan/.zjypy312/bin/activate && PYTHONPATH=. python -m pytest tests/test_save_digital_video.py -v --alluredir=reports/allure-results'并对结果进行分析",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        metadata={"current_round": 0}
    )
    
    
    tool_calls = []
    current_round = 0
    conversation = [user_msg]
    while current_round < 5:
        
        cur_content = ""
        async for chunk in await llm.generate(conversation):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                cur_content += chunk.content

            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
        
            if tool_calls:
                print("\n检测到工具调用:")
                conversation.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        content="",
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        tool_calls=tool_calls,
                        metadata={"current_round": current_round}
                    )
                )
                for tool_call in tool_calls:
                    print(f"  工具: {tool_call.function['name']}" )
                    print(f"  参数: {tool_call.function['arguments']}")
                    arguments = json.loads(tool_call.function['arguments'])
                    async for tool_result in file_tool(**arguments):
                        conversation.append(
                            Message(
                                role=MessageRole.TOOL,
                                content=str(tool_result),
                                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                tool_call_id=tool_call.id,
                                metadata={"current_round": current_round}
                            )
                        )
                tool_calls = []
                cur_content = ""
        current_round +=1        
                                
            

if __name__ == "__main__":
    import asyncio  
    asyncio.run(test_shell_tool())