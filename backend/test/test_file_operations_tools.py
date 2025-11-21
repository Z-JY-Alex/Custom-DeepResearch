from datetime import datetime
import os
import sys
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.llm.llm import OpenAILLM
from backend.tools.stream_file_operations import StreamFileOperationTool
from backend.tools.file_operations import FileReadTool
from backend.llm.base import LLMConfig, Message, MessageRole


async def test_shell_tool():
    file_read = FileReadTool()
    file_tool = StreamFileOperationTool()

    llm_config = LLMConfig(
        api_key="amep3rwbqWIpFoOnKpZw",
        base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
        max_tokens=64000,
        stream=True,
        tools=[file_read, file_tool]
    )

    llm = OpenAILLM(llm_config)

    user_msg = Message(
        role=MessageRole.USER,
        content="修改文件第2个print,使其输出'Hello, ChatGPT!'如果代码有其他问题请进行修改，文件路径：./test_indent_sample.py",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        metadata={"current_round": 0}
    )
    
    
    current_round = 0
    conversation = [user_msg]
    while current_round < 10:
        
        cur_content = ""
        tool_calls = []
        async for chunk in await llm.generate(conversation):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                cur_content += chunk.content
                if file_tool.is_active():
                    await file_tool.write_chunk(chunk)
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
        

        conversation.append(
            Message(
                role=MessageRole.ASSISTANT, content=cur_content,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        )

        if tool_calls:
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
                try:
                    arguments = json.loads(tool_call.function['arguments'])
                except json.JSONDecodeError as e:
                    print(f"  错误: 无法解析参数 JSON: {e}")
                    conversation.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=f"错误: 无法解析参数 JSON: {e}",
                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            tool_call_id=tool_call.id,
                            metadata={"current_round": current_round}
                        )
                    )
                    continue
                
                function_name = tool_call.function['name']
                if function_name == "file_read":
                    async for tool_result in file_read(**arguments):
                        print(f"  工具: {function_name} 结果: {tool_result}")
                        conversation.append(
                            Message(
                                role=MessageRole.TOOL,
                                content=str(tool_result),
                                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                tool_call_id=tool_call.id,
                                metadata={"current_round": current_round}
                            )
                        )
                else:
                    async for tool_result in file_tool(**arguments):
                        print(f"  工具: {function_name} 结果: {tool_result}")
                        conversation.append(
                            Message(
                                role=MessageRole.TOOL,
                                content=str(tool_result),
                                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                tool_call_id=tool_call.id,
                                metadata={"current_round": current_round}
                            )
                        )
            cur_content = ""
        current_round +=1        
                                

if __name__ == "__main__":

    import asyncio  
    asyncio.run(test_shell_tool())