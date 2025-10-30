"""
简单的TokenCounter测试脚本
"""
import asyncio
import os
import sys

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
try:
    from backend.llm import (
        TokenCounter,
        create_token_counter,
        count_message_tokens,
        count_messages_tokens,
        create_text_message,
        MessageRole,
    )
    print("✅ 成功导入TokenCounter模块")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)


def test_basic_functionality():
    """测试基本功能"""
    print("\n=== 基本功能测试 ===")
    
    # 创建Token计数器
    try:
        counter = TokenCounter("gpt-3.5-turbo")
        print(f"✅ 成功创建TokenCounter，模型: {counter.model_name}")
    except Exception as e:
        print(f"❌ 创建TokenCounter失败: {e}")
        return False
    
    # 测试文本token计算
    try:
        text = "Hello, world!"
        tokens = counter.count_text_tokens(text)
        print(f"✅ 文本 '{text}' 的token数: {tokens}")
        
        chinese_text = "你好，世界！"
        chinese_tokens = counter.count_text_tokens(chinese_text)
        print(f"✅ 中文文本 '{chinese_text}' 的token数: {chinese_tokens}")
    except Exception as e:
        print(f"❌ 文本token计算失败: {e}")
        return False
    
    return True


def test_message_counting():
    """测试消息token计算"""
    print("\n=== 消息Token计算测试 ===")
    
    try:
        counter = TokenCounter("gpt-3.5-turbo")
        
        # 创建测试消息
        user_msg = create_text_message(MessageRole.USER, "请帮我解释一下什么是人工智能？")
        assistant_msg = create_text_message(
            MessageRole.ASSISTANT, 
            "人工智能(AI)是计算机科学的一个分支，致力于创建能够执行通常需要人类智能的任务的系统。"
        )
        system_msg = create_text_message(MessageRole.SYSTEM, "你是一个有用的AI助手。")
        
        # 计算单个消息token
        user_result = counter.count_message_tokens(user_msg)
        print(f"✅ 用户消息token详情: {user_result}")
        
        assistant_result = counter.count_message_tokens(assistant_msg)
        print(f"✅ 助手消息token详情: {assistant_result}")
        
        # 计算消息列表token
        messages = [system_msg, user_msg, assistant_msg]
        list_result = counter.count_messages_tokens(messages)
        print(f"✅ 消息列表总计: {list_result['total_tokens']} tokens")
        print(f"✅ 消息数量: {list_result['message_count']}")
        print(f"✅ 按角色统计: {list_result['by_role']}")
        
    except Exception as e:
        print(f"❌ 消息token计算失败: {e}")
        return False
    
    return True


def test_cost_estimation():
    """测试成本估算"""
    print("\n=== 成本估算测试 ===")
    
    try:
        counter = TokenCounter("gpt-3.5-turbo")
        
        # 测试成本估算
        test_tokens = 1000
        cost_info = counter.estimate_cost(test_tokens)
        print(f"✅ {test_tokens} tokens 的成本估算:")
        print(f"   模型: {cost_info['model']}")
        print(f"   每1000token成本: ${cost_info['cost_per_1k_tokens']}")
        print(f"   预估总成本: ${cost_info['estimated_cost_usd']}")
        
    except Exception as e:
        print(f"❌ 成本估算失败: {e}")
        return False
    
    return True


def test_convenience_functions():
    """测试便捷函数"""
    print("\n=== 便捷函数测试 ===")
    
    try:
        # 测试便捷函数
        message = create_text_message(MessageRole.USER, "这是一个测试消息")
        
        # 使用便捷函数计算单个消息
        result1 = count_message_tokens(message, "gpt-3.5-turbo")
        print(f"✅ 便捷函数 - 单个消息: {result1['total_tokens']} tokens")
        
        # 使用便捷函数计算消息列表
        messages = [message]
        result2 = count_messages_tokens(messages, "gpt-3.5-turbo")
        print(f"✅ 便捷函数 - 消息列表: {result2['total_tokens']} tokens")
        
        # 使用便捷创建函数
        counter = create_token_counter("gpt-4")
        print(f"✅ 便捷创建函数 - 模型: {counter.model_name}")
        
    except Exception as e:
        print(f"❌ 便捷函数测试失败: {e}")
        return False
    
    return True


def test_real_scenario():
    """测试真实使用场景"""
    print("\n=== 真实场景测试 ===")
    
    try:
        counter = TokenCounter("gpt-3.5-turbo")
        
        # 模拟一个真实的对话
        conversation = [
            create_text_message(MessageRole.SYSTEM, "你是一个专业的Python编程助手。"),
            create_text_message(MessageRole.USER, "我想学习Python中的列表推导式，能给我一些例子吗？"),
            create_text_message(
                MessageRole.ASSISTANT,
                """当然！列表推导式是Python中一种简洁创建列表的方式。以下是一些例子：

1. 基础语法：
   squares = [x**2 for x in range(10)]  # [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]

2. 带条件过滤：
   even_squares = [x**2 for x in range(10) if x % 2 == 0]  # [0, 4, 16, 36, 64]

3. 处理字符串：
   words = ["hello", "world", "python"]
   lengths = [len(word) for word in words]  # [5, 5, 6]

列表推导式比传统的for循环更简洁高效！"""
            ),
            create_text_message(MessageRole.USER, "太棒了！还有嵌套列表推导式的例子吗？"),
            create_text_message(
                MessageRole.ASSISTANT,
                """嵌套列表推导式可以处理二维数据：

1. 创建矩阵：
   matrix = [[i*j for j in range(3)] for i in range(3)]
   # [[0, 0, 0], [0, 1, 2], [0, 2, 4]]

2. 展平嵌套列表：
   nested = [[1, 2], [3, 4], [5, 6]]
   flat = [item for sublist in nested for item in sublist]
   # [1, 2, 3, 4, 5, 6]

3. 过滤和转换：
   matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
   even_nums = [num for row in matrix for num in row if num % 2 == 0]
   # [2, 4, 6, 8]

注意嵌套层级不要太深，影响可读性！"""
            )
        ]
        
        # 获取完整的token分析
        summary = counter.get_token_usage_summary(conversation)
        distribution = counter.analyze_token_distribution(conversation)
        
        print(f"✅ 对话统计:")
        print(f"   总消息数: {summary['message_count']}")
        print(f"   总token数: {summary['total_tokens']}")
        print(f"   平均每条消息: {summary['average_tokens_per_message']:.1f} tokens")
        print(f"   预估成本: ${summary['cost_estimation']['estimated_cost_usd']:.6f}")
        print(f"   内容效率: {distribution['efficiency_score']:.1f}%")
        
        print(f"\n✅ 按角色统计:")
        for role, stats in summary['by_role'].items():
            print(f"   {role}: {stats['count']}条消息, {stats['tokens']} tokens")
        
        print(f"\n✅ Token分布:")
        for category, info in distribution['distribution'].items():
            print(f"   {category}: {info['tokens']} tokens ({info['percentage']:.1f}%)")
        
    except Exception as e:
        print(f"❌ 真实场景测试失败: {e}")
        return False
    
    return True


def main():
    """主测试函数"""
    print("🧪 开始TokenCounter功能测试\n")
    
    tests = [
        ("基本功能", test_basic_functionality),
        ("消息计数", test_message_counting),
        ("成本估算", test_cost_estimation),
        ("便捷函数", test_convenience_functions),
        ("真实场景", test_real_scenario),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"🔍 运行测试: {test_name}")
        print('='*50)
        
        try:
            if test_func():
                print(f"✅ {test_name}测试通过")
                passed += 1
            else:
                print(f"❌ {test_name}测试失败")
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
    
    print(f"\n{'='*50}")
    print(f"🎯 测试结果: {passed}/{total} 通过")
    print('='*50)
    
    if passed == total:
        print("🎉 所有测试通过！TokenCounter功能正常！")
    else:
        print("⚠️  部分测试失败，请检查代码！")
    
    return passed == total


if __name__ == "__main__":
    main()