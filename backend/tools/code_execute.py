# tools/code_execute.py
import asyncio
import sys
from io import StringIO
import traceback
from typing import Dict, Any, Optional, Literal

from backend.tools.base import BaseTool, ToolError, ToolCallResult


class CodeExecuteTool(BaseTool):
    """
    代码执行工具，支持执行Python代码。
    """
    
    name: str = "code_execute"
    description: str = "执行Python代码并返回结果"
    parameters: dict = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的Python代码"
            },
            "context": {
                "type": "object",
                "description": "执行代码时的上下文变量（可选）",
                "additionalProperties": True
            },
            "timeout": {
                "type": "number",
                "description": "执行超时时间（秒）",
                "default": 30
            },
            "capture_output": {
                "type": "boolean",
                "description": "是否捕获标准输出",
                "default": True
            },
            "safe_mode": {
                "type": "boolean",
                "description": "是否启用安全模式（限制某些危险操作）",
                "default": True
            }
        },
        "required": ["code"],
        "additionalProperties": False
    }
    
    async def execute(
        self,
        *,
        code: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: float = 30,
        capture_output: bool = True,
        safe_mode: bool = True,
        **kwargs
    ) -> ToolCallResult:
        """
        执行Python代码。
        
        参数：
        - code: 要执行的代码
        - context: 执行上下文
        - timeout: 超时时间
        - capture_output: 是否捕获输出
        - safe_mode: 是否启用安全模式
        """
        try:
            # 安全模式检查
            if safe_mode:
                # 检查危险关键字
                dangerous_keywords = [
                    '__import__', 'exec', 'eval', 'compile',
                    'open', 'file', 'input', 'raw_input',
                    'os.', 'subprocess.', 'sys.exit', 'quit'
                ]
                code_lower = code.lower()
                for keyword in dangerous_keywords:
                    if keyword in code_lower:
                        raise ToolError(f"安全模式下不允许使用 '{keyword}'")
            
            # 准备执行环境
            exec_globals = {
                '__builtins__': __builtins__,
                '__name__': '__main__',
            }
            
            # 添加上下文变量
            if context:
                exec_globals.update(context)
            
            # 捕获输出
            old_stdout = sys.stdout
            captured_output = StringIO() if capture_output else None
            
            async def run_code():
                try:
                    if capture_output:
                        sys.stdout = captured_output
                    
                    # 执行代码
                    exec(code, exec_globals)
                    
                    # 获取结果
                    result = None
                    # 尝试获取最后一个表达式的值
                    try:
                        # 尝试作为表达式计算
                        result = eval(code.strip().split('\n')[-1], exec_globals)
                    except:
                        # 如果不是表达式，则没有返回值
                        pass
                    
                    return result
                    
                finally:
                    sys.stdout = old_stdout
            
            # 带超时执行
            try:
                result = await asyncio.wait_for(run_code(), timeout=timeout)
            except asyncio.TimeoutError:
                raise ToolError(f"代码执行超时（{timeout}秒）")
            
            # 获取输出
            output_text = captured_output.getvalue() if capture_output else ""
            
            return ToolCallResult(
                tool_call_id="code_execute",
                result="代码执行成功",
                output={
                    "result": result,
                    "stdout": output_text,
                    "variables": {k: v for k, v in exec_globals.items() 
                                if not k.startswith('__') and k not in ['exec', 'eval']},
                    "execution_time": f"< {timeout}s"
                }
            )
            
        except ToolError:
            raise
        except Exception as e:
            # 获取详细的错误信息
            error_trace = traceback.format_exc()
            raise ToolError(f"代码执行错误: {str(e)}\n{error_trace}")