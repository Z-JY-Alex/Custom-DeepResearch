from datetime import datetime
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.llm.llm import OpenAILLM, LLMConfig

from backend.tools.file_operations import FileReadTool
from backend.tools.stream_file_operations import StreamFileOperationTool
from backend.llm.base import LLMConfig, Message, MessageRole


async def test_file_write_tool():

    file_read_tool = FileReadTool()
    file_tool = StreamFileOperationTool()

    llm_config = LLMConfig(
        api_key="amep3rwbqWIpFoOnKpZw",
        base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
        max_tokens=64000,
        stream=True,
        tools=[file_tool, file_read_tool]
    )

    llm = OpenAILLM(llm_config)

    user_msg = Message(
        role=MessageRole.USER,
        content=f"修改文件使其输出'Hello, ChatGPT!'，如果代码格式有错，帮我进行修改，文件路径：/mnt/e/zhihuishu/deepresearch/test_indent_sample.py，",
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
                # 如果文件保存已激活，同时写入文件
                if file_tool.is_active():
                    await file_tool.write_chunk(chunk)
                    
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
                    arguments = eval(tool_call.function['arguments'])
                    async for tool_result in file_tool(**arguments):
                        conversation.append(
                            Message(
                                role=MessageRole.TOOL,
                                content=tool_result,
                                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                tool_call_id=tool_call.id,
                                metadata={"current_round": current_round}
                            )
                        )
                tool_calls = []
                cur_content = ""
        current_round +=1        
                        
        # if file_tool.is_active():
        #     result = await file_tool.finalize()
        #     conversation.append(
        #         Message(
        #             role="tool",
        #             content=result,
        #             timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        #             tool_calls=tool_calls,
        #             metadata={"current_round": current_round}
        #         )
        #     )            
            

if __name__ == "__main__":
    import asyncio  
    asyncio.run(test_file_write_tool())