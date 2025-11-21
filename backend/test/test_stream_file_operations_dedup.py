"""
测试stream_file_operations的智能去重功能

测试场景：
1. 测试基本的去重功能
2. 测试忽略缩进的去重
3. 测试部分重复的检测
4. 测试无重复的正常场景
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加backend目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 再添加项目根目录
project_root = os.path.dirname(backend_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.tools.stream_file_operations import StreamFileOperationTool


async def test_deduplication():
    """测试智能去重功能"""
    print("=" * 60)
    print("测试智能去重功能")
    print("=" * 60)

    # 创建测试目录
    test_dir = Path("test_output")
    test_dir.mkdir(exist_ok=True)

    # 创建测试文件
    test_file = test_dir / "test_dedup.py"
    original_content = """def test_function():
    print("line 1")
    print("line 2")
    print("line 3")
    print("line 4")
    print("line 5")
"""

    test_file.write_text(original_content)
    print(f"\n✓ 创建测试文件: {test_file}")
    print(f"原始内容（6行）:\n{original_content}")

    # 测试场景1：新内容末尾包含重复（完全匹配）
    print("\n" + "-" * 60)
    print("测试场景1: 新内容末尾包含2行重复")
    print("-" * 60)

    tool = StreamFileOperationTool()

    # 开始修改操作（替换第2-5行）
    async for result in tool.execute(
        filepath=str(test_file),
        operation_mode="modify",
        start_line=2,
        end_line=5,
        status="start",
        auto_deduplicate=True,
        show_diff=True
    ):
        print(result)

    # 模拟LLM生成的内容（包含重复）
    # 新内容应该是4行，但LLM多生成了2行重复内容
    new_content_with_dup = """    print("new line A")
    print("new line B")
    print("line 4")
    print("line 5")"""

    # 分块写入内容（模拟流式生成）
    chunks = [new_content_with_dup[i:i+20] for i in range(0, len(new_content_with_dup), 20)]
    for chunk in chunks:
        await tool.write_chunk(chunk)

    # 完成操作
    async for result in tool.execute(
        filepath=str(test_file),
        status="end"
    ):
        print(result)

    # 读取并显示结果
    final_content = test_file.read_text()
    print(f"\n最终文件内容:\n{final_content}")

    # 测试场景2：新内容末尾包含部分重复（缩进不同）
    print("\n" + "-" * 60)
    print("测试场景2: 新内容末尾包含1行重复（缩进不同）")
    print("-" * 60)

    # 重置文件
    test_file.write_text(original_content)

    tool2 = StreamFileOperationTool()

    # 开始修改操作（替换第2-4行）
    async for result in tool2.execute(
        filepath=str(test_file),
        operation_mode="modify",
        start_line=2,
        end_line=4,
        status="start",
        auto_deduplicate=True,
        show_diff=True
    ):
        print(result)

    # 模拟LLM生成的内容（缩进不同的重复）
    new_content_indent_dup = """    print("new line X")
    print("new line Y")
print("line 3")"""  # 缩进不同，但内容相同

    chunks = [new_content_indent_dup]
    for chunk in chunks:
        await tool2.write_chunk(chunk)

    # 完成操作
    async for result in tool2.execute(
        filepath=str(test_file),
        status="end"
    ):
        print(result)

    # 读取并显示结果
    final_content = test_file.read_text()
    print(f"\n最终文件内容:\n{final_content}")

    # 测试场景3：无重复的正常场景
    print("\n" + "-" * 60)
    print("测试场景3: 无重复的正常场景")
    print("-" * 60)

    # 重置文件
    test_file.write_text(original_content)

    tool3 = StreamFileOperationTool()

    # 开始修改操作（替换第2-4行）
    async for result in tool3.execute(
        filepath=str(test_file),
        operation_mode="modify",
        start_line=2,
        end_line=4,
        status="start",
        auto_deduplicate=True,
        show_diff=True
    ):
        print(result)

    # 正常的新内容（无重复）
    normal_content = """    print("replaced line 1")
    print("replaced line 2")
    print("replaced line 3")"""

    chunks = [normal_content]
    for chunk in chunks:
        await tool3.write_chunk(chunk)

    # 完成操作
    async for result in tool3.execute(
        filepath=str(test_file),
        status="end"
    ):
        print(result)

    # 读取并显示结果
    final_content = test_file.read_text()
    print(f"\n最终文件内容:\n{final_content}")

    print("\n" + "=" * 60)
    print("✓ 所有测试完成")
    print("=" * 60)


async def test_direct_dedup_method():
    """直接测试去重方法"""
    print("\n\n" + "=" * 60)
    print("直接测试_remove_duplicate_suffix方法")
    print("=" * 60)

    tool = StreamFileOperationTool()

    # 测试用例1: 完全匹配的重复
    print("\n测试用例1: 完全匹配的重复")
    original = ["line 1", "line 2", "line 3", "line 4"]
    new_with_dup = ["new line A", "new line B", "line 3", "line 4"]

    result, removed = tool._remove_duplicate_suffix(new_with_dup, original)
    print(f"原始行: {original}")
    print(f"新行（含重复）: {new_with_dup}")
    print(f"去重后: {result}")
    print(f"移除行数: {removed}")
    assert removed == 2, f"预期移除2行，实际移除{removed}行"
    assert result == ["new line A", "new line B"], f"去重结果不符合预期"
    print("✓ 测试通过")

    # 测试用例2: 忽略缩进的重复
    print("\n测试用例2: 忽略缩进的重复")
    original2 = ["    line 1", "    line 2", "    line 3"]
    new_with_indent_dup = ["new line X", "line 3"]  # 缩进不同

    result2, removed2 = tool._remove_duplicate_suffix(new_with_indent_dup, original2)
    print(f"原始行: {original2}")
    print(f"新行（含重复）: {new_with_indent_dup}")
    print(f"去重后: {result2}")
    print(f"移除行数: {removed2}")
    assert removed2 == 1, f"预期移除1行，实际移除{removed2}行"
    assert result2 == ["new line X"], f"去重结果不符合预期"
    print("✓ 测试通过")

    # 测试用例3: 无重复
    print("\n测试用例3: 无重复")
    original3 = ["line 1", "line 2", "line 3"]
    new_no_dup = ["new line A", "new line B", "new line C"]

    result3, removed3 = tool._remove_duplicate_suffix(new_no_dup, original3)
    print(f"原始行: {original3}")
    print(f"新行（无重复）: {new_no_dup}")
    print(f"去重后: {result3}")
    print(f"移除行数: {removed3}")
    assert removed3 == 0, f"预期移除0行，实际移除{removed3}行"
    assert result3 == new_no_dup, f"去重结果不符合预期"
    print("✓ 测试通过")

    # 测试用例4: 部分重复（中间位置）
    print("\n测试用例4: 部分重复（原内容中间的片段）")
    original4 = ["line 1", "line 2", "line 3", "line 4", "line 5"]
    new_middle_dup = ["new A", "new B", "line 2", "line 3"]  # 重复原内容的中间部分

    result4, removed4 = tool._remove_duplicate_suffix(new_middle_dup, original4)
    print(f"原始行: {original4}")
    print(f"新行（含中间重复）: {new_middle_dup}")
    print(f"去重后: {result4}")
    print(f"移除行数: {removed4}")
    # 应该能检测到末尾2行与原内容的第2-3行匹配
    assert removed4 == 2, f"预期移除2行，实际移除{removed4}行"
    assert result4 == ["new A", "new B"], f"去重结果不符合预期"
    print("✓ 测试通过")

    print("\n" + "=" * 60)
    print("✓ 所有直接测试通过")
    print("=" * 60)


async def main():
    """运行所有测试"""
    try:
        # 先测试核心方法
        await test_direct_dedup_method()

        # 再测试完整流程
        await test_deduplication()

        print("\n\n🎉 所有测试成功完成！")

    except AssertionError as e:
        print(f"\n\n❌ 测试失败: {e}")
        raise
    except Exception as e:
        print(f"\n\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())
