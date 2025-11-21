"""
测试优化后的 StreamFileOperationTool 功能
- 智能缩进处理
- 文件差异显示
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.tools.stream_file_operations import StreamFileOperationTool


async def test_modify_with_auto_indent():
    """测试 modify 模式的智能缩进功能"""
    print("=" * 60)
    print("测试1: Modify 模式 - 智能缩进")
    print("=" * 60)

    # 创建测试文件
    test_file = Path("test_indent_sample.py")
    test_content = """def hello_world():
    print("Hello")
    if True:
        print("World")
        return True
"""
    test_file.write_text(test_content)

    # 创建工具实例
    tool = StreamFileOperationTool()

    # 开始 modify 操作 - 修改第4行（缩进为8个空格）
    print("\n开始 modify 操作，修改第4行...")
    async for result in tool.execute(
        filepath=str(test_file),
        operation_mode="modify",
        start_line=4,
        status="start",
        auto_indent=True,
        show_diff=True,
        diff_format="unified"
    ):
        print(result)

    # 写入新内容（不带缩进）
    new_content = 'print("Modified line")\nprint("Another line")'

    # 模拟流式写入
    for chunk in new_content:
        await tool.write_chunk(chunk)

    # 完成操作
    print("\n完成操作...")
    async for result in tool.execute(
        filepath=str(test_file),
        status="end"
    ):
        print(result)

    # 显示修改后的文件内容
    print("\n修改后的文件内容:")
    print("-" * 60)
    print(test_file.read_text())
    print("-" * 60)

    # 清理测试文件
    test_file.unlink()
    if test_file.with_suffix(".py.backup").exists():
        test_file.with_suffix(".py.backup").unlink()


async def test_insert_with_auto_indent():
    """测试 insert 模式的智能缩进功能"""
    print("\n" + "=" * 60)
    print("测试2: Insert 模式 - 智能缩进")
    print("=" * 60)

    # 创建测试文件
    test_file = Path("test_insert_sample.py")
    test_content = """class MyClass:
    def __init__(self):
        self.name = "test"

    def method1(self):
        pass
"""
    test_file.write_text(test_content)

    # 创建工具实例
    tool = StreamFileOperationTool()

    # 开始 insert 操作 - 在第5行前插入（缩进为4个空格）
    print("\n开始 insert 操作，在第5行前插入...")
    async for result in tool.execute(
        filepath=str(test_file),
        operation_mode="insert",
        start_line=5,
        status="start",
        auto_indent=True,
        show_diff=True,
        diff_format="simple"
    ):
        print(result)

    # 写入新内容（不带缩进）
    new_content = '''def new_method(self):
    """新增的方法"""
    return self.name
    '''

    # 模拟流式写入
    for chunk in new_content:
        await tool.write_chunk(chunk)

    # 完成操作
    print("\n完成操作...")
    async for result in tool.execute(
        filepath=str(test_file),
        status="end"
    ):
        print(result)

    # 显示修改后的文件内容
    print("\n修改后的文件内容:")
    print("-" * 60)
    print(test_file.read_text())
    print("-" * 60)

    # 清理测试文件
    test_file.unlink()
    if test_file.with_suffix(".py.backup").exists():
        test_file.with_suffix(".py.backup").unlink()


async def test_modify_without_auto_indent():
    """测试禁用智能缩进的情况"""
    print("\n" + "=" * 60)
    print("测试3: Modify 模式 - 禁用智能缩进")
    print("=" * 60)

    # 创建测试文件
    test_file = Path("test_no_indent_sample.py")
    test_content = """def function():
    if True:
        original_line = "test"
"""
    test_file.write_text(test_content)

    # 创建工具实例
    tool = StreamFileOperationTool()

    # 开始 modify 操作 - 禁用自动缩进
    print("\n开始 modify 操作，禁用自动缩进...")
    async for result in tool.execute(
        filepath=str(test_file),
        operation_mode="modify",
        start_line=3,
        status="start",
        auto_indent=False,
        show_diff=True,
        diff_format="unified"
    ):
        print(result)

    # 写入新内容（手动添加缩进）
    new_content = '        new_line = "manually indented"'

    # 模拟流式写入
    for chunk in new_content:
        await tool.write_chunk(chunk)

    # 完成操作
    print("\n完成操作...")
    async for result in tool.execute(
        filepath=str(test_file),
        status="end"
    ):
        print(result)

    # 显示修改后的文件内容
    print("\n修改后的文件内容:")
    print("-" * 60)
    print(test_file.read_text())
    print("-" * 60)

    # 清理测试文件
    test_file.unlink()
    if test_file.with_suffix(".py.backup").exists():
        test_file.with_suffix(".py.backup").unlink()


async def test_no_diff_display():
    """测试禁用差异显示的情况"""
    print("\n" + "=" * 60)
    print("测试4: Modify 模式 - 禁用差异显示")
    print("=" * 60)

    # 创建测试文件
    test_file = Path("test_no_diff_sample.txt")
    test_content = """Line 1
Line 2
Line 3
"""
    test_file.write_text(test_content)

    # 创建工具实例
    tool = StreamFileOperationTool()

    # 开始 modify 操作 - 禁用差异显示
    print("\n开始 modify 操作，禁用差异显示...")
    async for result in tool.execute(
        filepath=str(test_file),
        operation_mode="modify",
        start_line=2,
        status="start",
        show_diff=False
    ):
        print(result)

    # 写入新内容
    new_content = 'Modified Line 2'

    # 模拟流式写入
    for chunk in new_content:
        await tool.write_chunk(chunk)

    # 完成操作
    print("\n完成操作（不会显示diff）...")
    async for result in tool.execute(
        filepath=str(test_file),
        status="end"
    ):
        print(result)

    # 清理测试文件
    test_file.unlink()
    if test_file.with_suffix(".txt.backup").exists():
        test_file.with_suffix(".txt.backup").unlink()


async def main():
    """运行所有测试"""
    print("\n开始测试优化后的 StreamFileOperationTool\n")

    try:
        await test_modify_with_auto_indent()
        await test_insert_with_auto_indent()
        await test_modify_without_auto_indent()
        await test_no_diff_display()

        print("\n" + "=" * 60)
        print("所有测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
