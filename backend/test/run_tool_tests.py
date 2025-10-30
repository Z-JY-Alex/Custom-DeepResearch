#!/usr/bin/env python3
"""
运行文件操作和代码执行工具的测试
"""
import asyncio
import sys
import os

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))


async def main():
    """运行所有工具测试"""
    print("=" * 60)
    print("开始运行工具测试")
    print("=" * 60)
    
    # 运行文件操作工具测试
    print("\n>>> 运行文件操作工具测试...")
    try:
        from test_file_operations_tools import main as file_ops_main
        await file_ops_main()
        print("\n✓ 文件操作工具测试完成")
    except Exception as e:
        print(f"\n✗ 文件操作工具测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "-" * 60 + "\n")
    
    # 运行代码执行工具测试
    print(">>> 运行代码执行工具测试...")
    try:
        from test_code_execute_tool import main as code_exec_main
        await code_exec_main()
        print("\n✓ 代码执行工具测试完成")
    except Exception as e:
        print(f"\n✗ 代码执行工具测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("所有测试运行完成")
    print("=" * 60)


if __name__ == "__main__":
    # 设置事件循环
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行测试
    asyncio.run(main())