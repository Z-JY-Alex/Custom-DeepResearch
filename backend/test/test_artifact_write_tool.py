# test/test_artifact_write_tool.py
import asyncio
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.tools.artifact_write import ArtifactWriteTool
from backend.tools.base import ToolError


async def test_basic_artifact_creation():
    """测试基本的 artifact 创建"""
    print("测试基本的 artifact 创建...")
    
    tool = ArtifactWriteTool()
    test_content = "这是一个测试内容"
    
    try:
        result = await tool.execute(content=test_content)
        
        assert result.tool_call_id == "artifact_write"
        assert "工件创建成功" in result.result
        assert result.output["artifact_type"] == "text"
        assert result.output["content_length"] == len(test_content)
        
        print("✓ 基本 artifact 创建测试通过")
        return True
    except Exception as e:
        print(f"✗ 基本 artifact 创建测试失败: {e}")
        return False


async def test_artifact_with_parameters():
    """测试包含所有参数的 artifact 创建"""
    print("测试包含参数的 artifact 创建...")
    
    tool = ArtifactWriteTool()
    
    try:
        result = await tool.execute(
            content="详细的测试内容",
            artifact_type="file",
            name="测试工件",
            summary="这是一个测试摘要",
            tags=["测试", "示例"],
            content_location="/path/to/test/file.txt"
        )
        
        assert result.output["artifact_type"] == "file"
        assert result.output["name"] == "测试工件"
        assert result.output["summary"] == "这是一个测试摘要"
        assert result.output["tags"] == ["测试", "示例"]
        assert result.output["content_location"] == "/path/to/test/file.txt"
        
        print("✓ 带参数的 artifact 创建测试通过")
        return True
    except Exception as e:
        print(f"✗ 带参数的 artifact 创建测试失败: {e}")
        return False


async def test_empty_content_error():
    """测试空内容错误处理"""
    print("测试空内容错误处理...")
    
    tool = ArtifactWriteTool()
    
    try:
        await tool.execute(content="")
        print("✗ 空内容错误测试失败: 应该抛出异常但没有")
        return False
    except ToolError as e:
        if "内容不能为空" in str(e):
            print("✓ 空内容错误测试通过")
            return True
        else:
            print(f"✗ 空内容错误测试失败: 错误信息不符合预期: {e}")
            return False
    except Exception as e:
        print(f"✗ 空内容错误测试失败: 意外错误: {e}")
        return False


async def test_invalid_artifact_type():
    """测试无效的 artifact 类型"""
    print("测试无效的 artifact 类型...")
    
    tool = ArtifactWriteTool()
    
    try:
        await tool.execute(
            content="测试内容",
            artifact_type="invalid_type"
        )
        print("✗ 无效类型错误测试失败: 应该抛出异常但没有")
        return False
    except ToolError as e:
        if "不支持的工件类型" in str(e):
            print("✓ 无效类型错误测试通过")
            return True
        else:
            print(f"✗ 无效类型错误测试失败: 错误信息不符合预期: {e}")
            return False
    except Exception as e:
        print(f"✗ 无效类型错误测试失败: 意外错误: {e}")
        return False


async def test_different_artifact_types():
    """测试不同的 artifact 类型"""
    print("测试不同的 artifact 类型...")
    
    tool = ArtifactWriteTool()
    types_to_test = ["text", "file", "image", "audio", "video", "other"]
    
    success_count = 0
    for artifact_type in types_to_test:
        try:
            result = await tool.execute(
                content=f"测试 {artifact_type} 类型的内容",
                artifact_type=artifact_type
            )
            
            if result.output["artifact_type"] == artifact_type:
                success_count += 1
                print(f"  ✓ {artifact_type} 类型测试通过")
            else:
                print(f"  ✗ {artifact_type} 类型测试失败: 类型不匹配")
        except Exception as e:
            print(f"  ✗ {artifact_type} 类型测试失败: {e}")
    
    if success_count == len(types_to_test):
        print("✓ 所有 artifact 类型测试通过")
        return True
    else:
        print(f"✗ artifact 类型测试部分失败: {success_count}/{len(types_to_test)} 通过")
        return False


async def run_all_tests():
    """运行所有测试"""
    print("开始运行 ArtifactWriteTool 测试...\n")
    
    tests = [
        test_basic_artifact_creation,
        test_artifact_with_parameters,
        test_empty_content_error,
        test_invalid_artifact_type,
        test_different_artifact_types
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if await test():
            passed += 1
    
    
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过!")
        return True
    else:
        print("❌ 部分测试失败")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
