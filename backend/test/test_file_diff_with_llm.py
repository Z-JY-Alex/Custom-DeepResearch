from datetime import datetime
import os
import sys
import json
import asyncio
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.llm.llm import OpenAILLM, LLMConfig
from backend.tools.file_diff import FileDiffTool
from backend.llm.base import Message, MessageRole


async def setup_test_files():
    """创建测试文件用于比较"""
    test_dir = Path("backend/test/test_files")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建源文件
    source_file = test_dir / "source.py"
    source_content = """def hello():
    print("Hello, World!")
    return True

def add(a, b):
    return a + b

def multiply(x, y):
    return x * y
"""
    source_file.write_text(source_content, encoding='utf-8')
    
    # 创建目标文件（有修改）
    target_file = test_dir / "target.py"
    target_content = """def hello():
    print("Hello, World!")
    return True

def add(a, b):
    return a + b

def subtract(x, y):
    return x - y

def multiply(x, y):
    return x * y * 2
"""
    target_file.write_text(target_content, encoding='utf-8')
    
    # 创建备份文件
    backup_file = test_dir / "source.py.backup"
    backup_file.write_text(source_content, encoding='utf-8')
    
    print(f"✓ 测试文件已创建在: {test_dir}")
    # 返回相对路径（相对于项目根目录）
    base_dir = Path(".").resolve()
    # 确保文件路径是绝对路径后再计算相对路径
    return {
        "source": str(source_file.resolve().relative_to(base_dir)),
        "target": str(target_file.resolve().relative_to(base_dir)),
        "backup": str(backup_file.resolve().relative_to(base_dir))
    }


async def test_file_diff_tool_direct():
    """直接测试文件差异工具（不使用LLM）"""
    print("\n" + "="*60)
    print("直接测试 FileDiffTool")
    print("="*60)
    
    file_tool = FileDiffTool()
    
    # 设置测试文件
    test_files = await setup_test_files()
    
    # 测试1: 比较两个文件（unified格式）
    print("\n[测试1] 比较两个文件（unified格式）")
    print("-" * 60)
    async for result in file_tool(
        source_file=test_files["source"],
        target_file=test_files["target"],
        compare_mode="files",
        diff_format="unified"
    ):
        print(result)
    
    # 测试2: 比较文件与备份（context格式）
    print("\n[测试2] 比较文件与备份（context格式）")
    print("-" * 60)
    async for result in file_tool(
        source_file=test_files["source"],
        compare_mode="backup",
        diff_format="context",
        context_lines=2
    ):
        print(result)
    
    # 测试3: 比较文件与提供的内容（simple格式）
    print("\n[测试3] 比较文件与提供的内容（simple格式）")
    print("-" * 60)
    new_content = """def hello():
    print("Hello, New World!")
    return False
"""
    async for result in file_tool(
        source_file=test_files["source"],
        compare_mode="content",
        content=new_content,
        diff_format="simple"
    ):
        print(result)
    
    # 测试4: 测试ndiff格式
    print("\n[测试4] 使用ndiff格式比较")
    print("-" * 60)
    async for result in file_tool(
        source_file=test_files["source"],
        target_file=test_files["target"],
        compare_mode="files",
        diff_format="ndiff"
    ):
        print(result)


async def test_file_diff_with_llm():
    """使用LLM测试文件差异工具"""
    print("\n" + "="*60)
    print("使用LLM测试 FileDiffTool")
    print("="*60)
    
    file_tool = FileDiffTool()
    
    # 设置测试文件
    test_files = await setup_test_files()
    
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
        content=f"请帮我比较两个文件的差异：源文件是 '{test_files['source']}'，目标文件是 '{test_files['target']}'。使用unified格式显示差异，并分析这些修改的意义。",
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
                    content=cur_content if cur_content else "",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    tool_calls=tool_calls,
                    metadata={"current_round": current_round}
                )
            )
            
            for tool_call in tool_calls:
                print(f"  工具: {tool_call.function['name']}")
                print(f"  参数: {tool_call.function['arguments']}")
                arguments = json.loads(tool_call.function['arguments'])
                
                print("\n工具执行结果:")
                print("-" * 60)
                async for tool_result in file_tool(**arguments):
                    result_str = str(tool_result)
                    print(result_str)
                    conversation.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=result_str,
                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            tool_call_id=tool_call.id,
                            metadata={"current_round": current_round}
                        )
                    )
                print("-" * 60)
            
            tool_calls = []
            cur_content = ""
        
        # 如果没有工具调用，说明对话结束
        if not tool_calls and cur_content:
            conversation.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=cur_content,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    metadata={"current_round": current_round}
                )
            )
            break
        
        current_round += 1


async def test_file_diff_edge_cases():
    """测试边界情况"""
    print("\n" + "="*60)
    print("测试边界情况")
    print("="*60)
    
    file_tool = FileDiffTool()
    
    # 测试1: 文件不存在
    print("\n[边界测试1] 文件不存在")
    print("-" * 60)
    async for result in file_tool(
        source_file="backend/test/test_files/nonexistent.py",
        target_file="backend/test/test_files/also_nonexistent.py",
        compare_mode="files"
    ):
        print(result)
    
    # 测试2: 相同文件比较
    print("\n[边界测试2] 相同文件比较")
    print("-" * 60)
    test_files = await setup_test_files()
    async for result in file_tool(
        source_file=test_files["source"],
        target_file=test_files["source"],
        compare_mode="files"
    ):
        print(result)
    
    # 测试3: 忽略空白字符
    print("\n[边界测试3] 忽略空白字符比较")
    print("-" * 60)
    async for result in file_tool(
        source_file=test_files["source"],
        target_file=test_files["target"],
        compare_mode="files",
        ignore_whitespace=True
    ):
        print(result)


async def main():
    """主测试函数"""
    print("="*60)
    print("FileDiffTool 测试套件")
    print("="*60)
    
    try:
        # 测试1: 直接测试工具
        # await test_file_diff_tool_direct()
        
        # 测试2: 使用LLM测试
        await test_file_diff_with_llm()
        
        # 测试3: 边界情况
        await test_file_diff_edge_cases()
        
        print("\n" + "="*60)
        print("所有测试完成！")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

