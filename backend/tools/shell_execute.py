# tools/shell_execute.py
import asyncio
import subprocess
import sys
import os
import signal
from typing import Dict, Any, Optional, List, Union
import shlex
import platform

from backend.tools.base import BaseTool, ToolError, ToolCallResult


_SHELL_DERSCRIPTION = """
Shell命令执行工具，用于在指定环境中安全执行系统命令或脚本并获取结果。  

功能特点：
- 支持执行任意Shell命令或脚本，包括管道、重定向等复杂操作。
- 可指定工作目录（cwd）、环境变量（env）和执行器（executable）。
- 支持捕获标准输出和标准错误，可配置输出编码。
- 可设置执行超时时间，防止命令无限挂起。
- 提供安全模式选项，可限制潜在危险命令，保障系统安全。
"""


class ShellExecuteTool(BaseTool):
    """
    Shell命令执行工具，支持执行系统命令和shell脚本。
    """
    
    name: str = "shell_execute"
    description: str = _SHELL_DERSCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的shell命令或脚本"
            },
            "cwd": {
                "type": "string", 
                "description": "执行命令的工作目录（可选）",
                "default": None
            },
            "env": {
                "type": "object",
                "description": "环境变量（可选）",
                "additionalProperties": True
            },
            "timeout": {
                "type": "number",
                "description": "执行超时时间（秒）",
                "default": 30
            },
            "shell": {
                "type": "boolean",
                "description": "是否通过shell执行（True时支持管道等shell特性）",
                "default": True
            },
            "capture_output": {
                "type": "boolean",
                "description": "是否捕获输出",
                "default": True
            },
            "safe_mode": {
                "type": "boolean",
                "description": "是否启用安全模式（限制危险命令）",
                "default": True
            },
            "encoding": {
                "type": "string",
                "description": "输出编码",
                "default": "utf-8"
            },
            "executable": {
                "type": "string",
                "description": "指定shell执行器路径（如/bin/bash，用于执行bash特定命令）",
                "default": "/bin/bash"
            }
        },
        "required": ["command"],
        "additionalProperties": False
    }
    
    # 危险命令列表（安全模式下禁止）
    DANGEROUS_COMMANDS: List[str] = [
        "rm -rf /",
        "rm -rf /*",
        "dd if=/dev/zero",
        "mkfs",
        "format",
        "> /dev/sda",
        "chmod -R 777 /",
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        ":(){:|:&};:",  # Fork bomb
    ]
    
    # 需要警告的命令
    WARNING_COMMANDS: List[str] = [
        "rm ",
        "mv ",
        "chmod ",
        "chown ",
        "sudo ",
        "su ",
        "kill ",
        "pkill ",
        "killall ",
    ]
    
    async def execute(
        self,
        *,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30,
        shell: bool = True,
        capture_output: bool = True,
        safe_mode: bool = True,
        encoding: str = "utf-8",
        executable: Optional[str] = "/bin/bash",
        **kwargs
    ) -> ToolCallResult:
        """
        执行shell命令。
        
        参数：
        - command: 要执行的命令
        - cwd: 工作目录
        - env: 环境变量
        - timeout: 超时时间
        - shell: 是否使用shell执行
        - capture_output: 是否捕获输出
        - safe_mode: 是否启用安全模式
        - encoding: 输出编码
        - executable: 指定shell执行器（如/bin/bash）
        """
        try:
            # 安全检查
            if safe_mode:
                self._safety_check(command)
            
            # 准备环境变量
            process_env = os.environ.copy()
            if env:
                process_env.update(env)
            
            # 默认使用bash执行器，除非明确指定为None
            if shell and executable is None:
                executable = "/bin/bash"
            
            # 准备命令
            if not shell and isinstance(command, str):
                # 如果不使用shell，需要分割命令
                command_list = shlex.split(command)
            else:
                command_list = command
            
            # 创建进程
            start_time = asyncio.get_event_loop().time()
            
            if capture_output:
                if executable and shell:
                    process = await asyncio.create_subprocess_exec(
                        executable, "-c", command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=cwd,
                        env=process_env
                    )
                else:
                    process = await asyncio.create_subprocess_shell(
                        command if shell else shlex.join(command_list),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=cwd,
                        env=process_env,
                        shell=shell
                    )
            else:
                if executable and shell:
                    process = await asyncio.create_subprocess_exec(
                        executable, "-c", command,
                        cwd=cwd,
                        env=process_env
                    )
                else:
                    process = await asyncio.create_subprocess_shell(
                        command if shell else shlex.join(command_list),
                        cwd=cwd,
                        env=process_env,
                        shell=shell
                    )
            
            try:
                # 等待进程完成
                if capture_output:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=timeout
                    )
                    stdout_text = stdout.decode(encoding, errors='replace').strip() if stdout else ""
                    stderr_text = stderr.decode(encoding, errors='replace').strip() if stderr else ""
                else:
                    await asyncio.wait_for(
                        process.wait(),
                        timeout=timeout
                    )
                    stdout_text = ""
                    stderr_text = ""
                    
            except asyncio.TimeoutError:
                # 超时处理
                try:
                    # 尝试优雅终止
                    process.terminate()
                    await asyncio.sleep(0.5)
                    if process.returncode is None:
                        # 强制终止
                        process.kill()
                        await process.wait()
                except:
                    pass
                
                raise ToolError(f"命令执行超时（{timeout}秒）: {command}")
            
            # 计算执行时间
            execution_time = asyncio.get_event_loop().time() - start_time
            
            # 检查返回码
            if process.returncode != 0:
                # 返回错误结果而不是抛出异常，让用户看到输出
                return ToolCallResult(
                    tool_call_id="shell_execute",
                    result=f"RETURN_CODE: {process.returncode}\n{stdout_text}\n{stderr_text}",
                    error=f"RETURN_CODE: {process.returncode}\n{stdout_text}\n{stderr_text}",
                    output={
                        "command": command,
                        "return_code": process.returncode,
                        "stdout": stdout_text,
                        "stderr": stderr_text,
                        "execution_time": f"{execution_time:.2f}s",
                        "cwd": cwd or os.getcwd()
                    }
                )
            
            # 返回成功结果
            return ToolCallResult(
                tool_call_id="shell_execute",
                result=f"RETURN_CODE: {process.returncode}\n{stdout_text}\n{stderr_text}",
                output={
                    "command": command,
                    "return_code": process.returncode,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "execution_time": f"{execution_time:.2f}s",
                    "cwd": cwd or os.getcwd(),
                    "platform": platform.system()
                }
            )
            
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"命令执行错误: {str(e)}")
    
    def _safety_check(self, command: str) -> None:
        """
        安全检查，防止执行危险命令。
        
        参数：
        - command: 要检查的命令
        """
        command_lower = command.lower().strip()
        
        # 检查绝对危险命令
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous.lower() in command_lower:
                raise ToolError(
                    f"安全模式下不允许执行危险命令: {dangerous}\n"
                    f"如果确实需要执行，请设置 safe_mode=False"
                )
        
        # 检查需要警告的命令
        warnings = []
        for warning_cmd in self.WARNING_COMMANDS:
            if warning_cmd.lower() in command_lower:
                warnings.append(warning_cmd.strip())
        
        if warnings:
            # 这里只是记录，不阻止执行
            # 在实际使用中可以通过日志系统记录
            pass
    
    def _requires_bash(self, command: str) -> bool:
        """
        检测命令是否需要bash执行器。
        
        参数：
        - command: 要检查的命令
        
        返回：
        - 是否需要bash
        """
        bash_features = [
            "source ",      # bash内置命令
            "[[",          # bash条件测试
            "function ",   # bash函数定义
            "declare ",    # bash变量声明
            "local ",      # bash局部变量
            "export -f",   # bash函数导出
            "pushd ",      # bash目录栈
            "popd",        # bash目录栈
            "shopt ",      # bash选项设置
            "set -o",      # bash选项设置
        ]
        
        command_lower = command.lower()
        return any(feature in command_lower for feature in bash_features)
    
    @staticmethod
    def escape_shell_arg(arg: str) -> str:
        """
        转义shell参数，防止注入。
        
        参数：
        - arg: 要转义的参数
        
        返回：
        - 转义后的参数
        """
        return shlex.quote(arg)
    
    @staticmethod
    def build_command(command: str, args: List[str]) -> str:
        """
        构建安全的命令行。
        
        参数：
        - command: 命令名
        - args: 参数列表
        
        返回：
        - 完整的命令行
        """
        safe_args = [ShellExecuteTool.escape_shell_arg(arg) for arg in args]
        return f"{command} {' '.join(safe_args)}"