
"""
代码执行工具测试
"""
import asyncio
import os
import sys
import time

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.tools.code_execute import CodeExecuteTool
from backend.tools.base import ToolError


async def test_basic_execution():
    """测试基础代码执行"""
    print("=== 基础代码执行测试 ===")
    
    exec_tool = CodeExecuteTool()
    
    # 测试1: 简单计算
    print("\n1. 测试简单计算")
    code = """
x = 10
y = 20
result = x + y
print(f"计算结果: {x} + {y} = {result}")
result
"""
    
    try:
        result = await exec_tool.execute(code=code)
        print(f"✓ 执行成功: {result.result}")
        print(f"  返回值: {result.output['result']}")
        print(f"  标准输出: {repr(result.output['stdout'])}")
        assert result.output['result'] == 30
        assert "计算结果: 10 + 20 = 30" in result.output['stdout']
        print("✓ 结果验证通过")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return
    
    # 测试2: 字符串操作
    print("\n2. 测试字符串操作")
    code = """
text = "Hello, World!"
upper_text = text.upper()
parts = text.split(", ")
print(f"原始文本: {text}")
print(f"大写: {upper_text}")
print(f"分割结果: {parts}")
{"upper": upper_text, "parts": parts, "length": len(text)}
"""
    
    try:
        result = await exec_tool.execute(code=code)
        print(f"✓ 执行成功")
        output = result.output['result']
        assert output['upper'] == "HELLO, WORLD!"
        assert output['parts'] == ["Hello", "World!"]
        assert output['length'] == 13
        print("✓ 字符串操作验证通过")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return
    
    # 测试3: 列表和字典操作
    print("\n3. 测试列表和字典操作")
    code = """
# 列表操作
numbers = [1, 2, 3, 4, 5]
squared = [x**2 for x in numbers]
total = sum(squared)

# 字典操作
data = {"a": 1, "b": 2, "c": 3}
keys = list(data.keys())
values = list(data.values())

print(f"原始数字: {numbers}")
print(f"平方后: {squared}")
print(f"总和: {total}")
print(f"字典键: {keys}")

{"squared": squared, "total": total, "dict_sum": sum(values)}
"""
    
    try:
        result = await exec_tool.execute(code=code)
        print(f"✓ 执行成功")
        output = result.output['result']
        assert output['squared'] == [1, 4, 9, 16, 25]
        assert output['total'] == 55
        assert output['dict_sum'] == 6
        print("✓ 数据结构操作验证通过")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return


async def test_context_execution():
    """测试带上下文的代码执行"""
    print("\n\n=== 上下文代码执行测试 ===")
    
    exec_tool = CodeExecuteTool()
    
    # 测试1: 使用预定义变量
    print("\n1. 测试使用预定义变量")
    context = {
        "users": ["Alice", "Bob", "Charlie"],
        "scores": {"Alice": 85, "Bob": 92, "Charlie": 78},
        "passing_score": 80
    }
    
    code = """
# 使用上下文中的变量
passed_users = [user for user in users if scores[user] >= passing_score]
failed_users = [user for user in users if scores[user] < passing_score]
average_score = sum(scores.values()) / len(scores)

print(f"总用户数: {len(users)}")
print(f"及格分数: {passing_score}")
print(f"及格用户: {passed_users}")
print(f"不及格用户: {failed_users}")
print(f"平均分: {average_score:.1f}")

{
    "passed": passed_users,
    "failed": failed_users,
    "average": average_score,
    "pass_rate": len(passed_users) / len(users)
}
"""
    
    try:
        result = await exec_tool.execute(code=code, context=context)
        print(f"✓ 执行成功")
        output = result.output['result']
        assert output['passed'] == ["Alice", "Bob"]
        assert output['failed'] == ["Charlie"]
        assert output['pass_rate'] == 2/3
        print("✓ 上下文变量使用验证通过")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return
    
    # 测试2: 修改上下文变量
    print("\n2. 测试修改上下文变量")
    context = {"counter": 0, "items": []}
    
    code = """
# 修改上下文中的变量
for i in range(5):
    counter += 1
    items.append(f"item_{counter}")

print(f"最终计数: {counter}")
print(f"项目列表: {items}")

{"counter": counter, "items": items}
"""
    
    try:
        result = await exec_tool.execute(code=code, context=context)
        print(f"✓ 执行成功")
        # 检查变量
        variables = result.output['variables']
        assert variables['counter'] == 5
        assert len(variables['items']) == 5
        print("✓ 上下文修改验证通过")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return


async def test_output_capture():
    """测试输出捕获"""
    print("\n\n=== 输出捕获测试 ===")
    
    exec_tool = CodeExecuteTool()
    
    # 测试1: 捕获标准输出
    print("\n1. 测试捕获标准输出")
    code = """
print("第一行输出")
print("第二行输出")
for i in range(3):
    print(f"  循环 {i}")
print("最后一行")
"执行完成"
"""
    
    try:
        # 启用捕获
        result = await exec_tool.execute(code=code, capture_output=True)
        print(f"✓ 捕获输出成功")
        stdout = result.output['stdout']
        assert "第一行输出" in stdout
        assert "循环 0" in stdout
        assert "循环 1" in stdout
        assert "循环 2" in stdout
        assert "最后一行" in stdout
        print(f"  捕获的输出行数: {len(stdout.splitlines())}")
        
        # 禁用捕获
        result = await exec_tool.execute(code=code, capture_output=False)
        assert result.output['stdout'] == ""
        print("✓ 禁用捕获验证通过")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return
    
    # 测试2: 捕获大量输出
    print("\n2. 测试捕获大量输出")
    code = """
for i in range(100):
    print(f"Line {i}: " + "x" * 50)
print("完成")
"done"
"""
    
    try:
        result = await exec_tool.execute(code=code, capture_output=True)
        stdout = result.output['stdout']
        lines = stdout.splitlines()
        assert len(lines) == 101  # 100行 + "完成"
        assert all(f"Line {i}:" in lines[i] for i in range(100))
        print(f"✓ 大量输出捕获成功，共 {len(lines)} 行")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return


async def test_safety_mode():
    """测试安全模式"""
    print("\n\n=== 安全模式测试 ===")
    
    exec_tool = CodeExecuteTool()
    
    # 测试1: 危险操作检测
    print("\n1. 测试危险操作检测")
    dangerous_operations = [
        ("文件操作", "open('/etc/passwd', 'r')", "open"),
        ("导入模块", "__import__('os')", "__import__"),
        ("执行代码", "exec('print(1)')", "exec"),
        ("评估表达式", "eval('1+1')", "eval"),
        ("编译代码", "compile('1+1', 'string', 'eval')", "compile"),
        ("系统调用", "import os; os.system('ls')", "os."),
        ("子进程", "import subprocess; subprocess.run(['ls'])", "subprocess."),
        ("退出程序", "import sys; sys.exit()", "sys.exit"),
    ]
    
    for desc, code, keyword in dangerous_operations:
        try:
            await exec_tool.execute(code=code, safe_mode=True)
            print(f"✗ {desc} 应该被阻止")
        except ToolError as e:
            # 错误信息应该包含安全模式的提示
            error_msg = str(e)
            if "安全模式下不允许使用" in error_msg:
                print(f"✓ {desc} 被正确阻止: {error_msg}")
            else:
                print(f"✗ {desc} 错误信息不正确: {error_msg}")
                raise
    
    # 测试2: 关闭安全模式
    print("\n2. 测试关闭安全模式")
    code = """
# 在关闭安全模式下执行
result = eval('10 + 20')
print(f"eval结果: {result}")
result
"""
    
    try:
        result = await exec_tool.execute(code=code, safe_mode=False)
        assert result.output['result'] == 30
        print("✓ 关闭安全模式后可以执行危险操作")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return
    
    # 测试3: 安全的代码执行
    print("\n3. 测试安全的代码执行")
    safe_code = """
# 这些操作在安全模式下是允许的
import math
import json
import datetime

# 数学运算
sqrt_result = math.sqrt(16)
print(f"平方根: {sqrt_result}")

# JSON操作
data = {"key": "value"}
json_str = json.dumps(data)
print(f"JSON: {json_str}")

# 日期时间
now = datetime.datetime.now()
print(f"当前时间: {now}")

{"sqrt": sqrt_result, "json": json_str}
"""
    
    try:
        result = await exec_tool.execute(code=safe_code, safe_mode=True)
        print("✓ 安全代码执行成功")
        assert result.output['result']['sqrt'] == 4.0
        print("✓ 安全操作验证通过")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return


async def test_timeout():
    """测试超时处理"""
    print("\n\n=== 超时处理测试 ===")
    
    exec_tool = CodeExecuteTool()
    
    # 测试1: 超时检测
    print("\n1. 测试超时检测")
    timeout_code = """
import time
print("开始执行长时间任务...")
time.sleep(3)  # 睡眠3秒
print("这行不应该被执行")
"不应该返回"
"""
    
    try:
        # 设置1秒超时
        await exec_tool.execute(code=timeout_code, timeout=1)
        print("✗ 应该超时")
    except ToolError as e:
        assert "代码执行超时" in str(e)
        print(f"✓ 正确检测到超时: {e}")
    
    # 测试2: 正常执行不超时
    print("\n2. 测试正常执行不超时")
    normal_code = """
import time
print("开始执行...")
time.sleep(0.5)  # 睡眠0.5秒
print("执行完成")
"成功"
"""
    
    try:
        result = await exec_tool.execute(code=normal_code, timeout=2)
        assert result.output['result'] == "成功"
        assert "执行完成" in result.output['stdout']
        print("✓ 正常执行未超时")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return
    
    # 测试3: 自定义超时时间
    print("\n3. 测试自定义超时时间")
    code = """
import time
for i in range(5):
    print(f"步骤 {i+1}/5")
    time.sleep(0.8)
"完成"
"""
    
    try:
        # 5秒超时应该成功
        result = await exec_tool.execute(code=code, timeout=5)
        assert result.output['result'] == "完成"
        print("✓ 自定义超时时间生效")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return


async def test_error_handling():
    """测试错误处理"""
    print("\n\n=== 错误处理测试 ===")
    
    exec_tool = CodeExecuteTool()
    
    # 测试1: 语法错误
    print("\n1. 测试语法错误")
    syntax_error_code = """
def test(:  # 语法错误
    print("test")
"""
    
    try:
        await exec_tool.execute(code=syntax_error_code)
        print("✗ 应该抛出异常")
    except ToolError as e:
        assert "SyntaxError" in str(e)
        print(f"✓ 正确捕获语法错误: SyntaxError")
    
    # 测试2: 运行时错误
    print("\n2. 测试运行时错误")
    runtime_error_code = """
x = 10
y = 0
result = x / y  # ZeroDivisionError
"""
    
    try:
        await exec_tool.execute(code=runtime_error_code)
        print("✗ 应该抛出异常")
    except ToolError as e:
        assert "ZeroDivisionError" in str(e)
        print(f"✓ 正确捕获运行时错误: ZeroDivisionError")
    
    # 测试3: 名称错误
    print("\n3. 测试名称错误")
    name_error_code = """
print(undefined_variable)  # NameError
"""
    
    try:
        await exec_tool.execute(code=name_error_code)
        print("✗ 应该抛出异常")
    except ToolError as e:
        assert "NameError" in str(e)
        print(f"✓ 正确捕获名称错误: NameError")
    
    # 测试4: 类型错误
    print("\n4. 测试类型错误")
    type_error_code = """
text = "hello"
result = text + 123  # TypeError
"""
    
    try:
        await exec_tool.execute(code=type_error_code)
        print("✗ 应该抛出异常")
    except ToolError as e:
        assert "TypeError" in str(e)
        print(f"✓ 正确捕获类型错误: TypeError")
    
    # 测试5: 索引错误
    print("\n5. 测试索引错误")
    index_error_code = """
lst = [1, 2, 3]
value = lst[10]  # IndexError
"""
    
    try:
        await exec_tool.execute(code=index_error_code)
        print("✗ 应该抛出异常")
    except ToolError as e:
        assert "IndexError" in str(e)
        print(f"✓ 正确捕获索引错误: IndexError")


async def test_complex_scenarios():
    """测试复杂场景"""
    print("\n\n=== 复杂场景测试 ===")
    
    exec_tool = CodeExecuteTool()
    
    # 测试1: 函数定义和调用
    print("\n1. 测试函数定义和调用")
    code = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

# 计算前10个斐波那契数
fib_numbers = [fibonacci(i) for i in range(10)]
print(f"斐波那契数列: {fib_numbers}")

# 计算阶乘
def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n-1)

fact_5 = factorial(5)
print(f"5! = {fact_5}")

{"fibonacci": fib_numbers, "factorial": fact_5}
"""
    
    try:
        result = await exec_tool.execute(code=code)
        output = result.output['result']
        assert output['fibonacci'] == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
        assert output['factorial'] == 120
        print("✓ 函数定义和递归调用成功")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return
    
    # 测试2: 类定义和使用
    print("\n2. 测试类定义和使用")
    code = """
class Calculator:
    def __init__(self, name="计算器"):
        self.name = name
        self.history = []
    
    def add(self, a, b):
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result
    
    def multiply(self, a, b):
        result = a * b
        self.history.append(f"{a} × {b} = {result}")
        return result
    
    def get_history(self):
        return self.history

# 创建实例并使用
calc = Calculator("我的计算器")
sum_result = calc.add(10, 20)
mult_result = calc.multiply(5, 6)
history = calc.get_history()

print(f"计算器名称: {calc.name}")
print(f"加法结果: {sum_result}")
print(f"乘法结果: {mult_result}")
print(f"历史记录: {history}")

{"sum": sum_result, "product": mult_result, "history": history}
"""
    
    try:
        result = await exec_tool.execute(code=code)
        output = result.output['result']
        assert output['sum'] == 30
        assert output['product'] == 30
        assert len(output['history']) == 2
        print("✓ 类定义和面向对象编程成功")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return
    
    # 测试3: 导入模块和使用
    print("\n3. 测试导入模块和使用")
    code = """
import json
import datetime
import math

# 使用json模块
data = {"name": "测试", "value": 42}
json_str = json.dumps(data, ensure_ascii=False)
parsed = json.loads(json_str)

# 使用datetime模块
now = datetime.datetime.now()
date_str = now.strftime("%Y-%m-%d")

# 使用math模块
circle_area = math.pi * (5 ** 2)
sqrt_2 = math.sqrt(2)

print(f"JSON序列化: {json_str}")
print(f"JSON解析: {parsed}")
print(f"日期: {date_str}")
print(f"圆面积 (r=5): {circle_area:.2f}")
print(f"√2 = {sqrt_2:.4f}")

{
    "json_works": parsed == data,
    "date_format": len(date_str) == 10,
    "pi": math.pi,
    "area": circle_area
}
"""
    
    try:
        result = await exec_tool.execute(code=code, safe_mode=False)
        output = result.output['result']
        assert output['json_works'] == True
        assert output['date_format'] == True
        assert abs(output['area'] - 78.54) < 0.01
        print("✓ 模块导入和使用成功")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return


async def test_performance():
    """测试性能相关场景"""
    print("\n\n=== 性能测试 ===")
    
    exec_tool = CodeExecuteTool()
    
    # 测试1: 大数据处理
    print("\n1. 测试大数据处理")
    code = """
# 生成大列表
big_list = list(range(10000))

# 列表推导式
squared = [x**2 for x in big_list[:100]]

# 过滤操作
evens = [x for x in big_list if x % 2 == 0]

# 统计
total = sum(big_list)
count = len(big_list)
even_count = len(evens)

print(f"列表大小: {count}")
print(f"偶数个数: {even_count}")
print(f"总和: {total}")

{"count": count, "even_count": even_count, "sum": total}
"""
    
    try:
        start_time = time.time()
        result = await exec_tool.execute(code=code)
        exec_time = time.time() - start_time
        
        output = result.output['result']
        assert output['count'] == 10000
        assert output['even_count'] == 5000
        assert output['sum'] == 49995000
        print(f"✓ 大数据处理成功，执行时间: {exec_time:.2f}秒")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return
    
    # 测试2: 复杂计算
    print("\n2. 测试复杂计算")
    code = """
import math

# 素数判断函数
def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return False
    return True

# 找出前100个素数
primes = []
num = 2
while len(primes) < 100:
    if is_prime(num):
        primes.append(num)
    num += 1

print(f"前10个素数: {primes[:10]}")
print(f"第100个素数: {primes[-1]}")

{"first_10": primes[:10], "100th": primes[-1], "count": len(primes)}
"""
    
    try:
        result = await exec_tool.execute(code=code)
        output = result.output['result']
        assert output['first_10'] == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
        assert output['100th'] == 541
        assert output['count'] == 100
        print("✓ 复杂计算成功")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return


async def main():
    """运行所有测试"""
    try:
        await test_basic_execution()
        await test_context_execution()
        await test_output_capture()
        await test_safety_mode()
        await test_timeout()
        await test_error_handling()
        await test_complex_scenarios()
        await test_performance()
        
        print("\n\n=== 所有代码执行测试通过! ✓ ===")
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())