# tools/file_operations.py
import os
import json
import aiofiles
from typing import Dict, Optional, Union
from pathlib import Path

from backend.tools.base import BaseTool, ToolError, ToolCallResult


class FileSaveTool(BaseTool):
    """
    文件保存工具，支持保存文本和JSON数据到文件。
    """
    
    name: str = "file_save"
    description: str = "保存内容到文件，支持文本和JSON格式"
    parameters: dict = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要保存的文件路径（相对或绝对路径）"
            },
            "content": {
                "type": ["string", "object", "array"],
                "description": "要保存的内容，可以是字符串或JSON对象/数组"
            },
            "mode": {
                "type": "string",
                "enum": ["text", "json"],
                "description": "保存模式：text（文本）或json（JSON格式）",
                "default": "text"
            },
            "encoding": {
                "type": "string",
                "description": "文件编码格式",
                "default": "utf-8"
            },
            "create_dirs": {
                "type": "boolean",
                "description": "如果目录不存在是否自动创建",
                "default": True
            }
        },
        "required": ["file_path", "content"],
        "additionalProperties": False
    }
    
    async def execute(
        self,
        *,
        file_path: str,
        content: Union[str, Dict, list],
        mode: str = "text",
        encoding: str = "utf-8",
        create_dirs: bool = True,
        **kwargs
    ) -> ToolCallResult:
        """
        执行文件保存操作。
        
        参数：
        - file_path: 文件路径
        - content: 要保存的内容
        - mode: 保存模式（text或json）
        - encoding: 文件编码
        - create_dirs: 是否自动创建目录
        """
        try:
            # 转换为Path对象
            path = Path(file_path)
            
            # 创建目录（如果需要）
            if create_dirs and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            
            # 根据模式处理内容
            if mode == "json":
                if isinstance(content, str):
                    # 如果是字符串，尝试解析为JSON
                    try:
                        json.loads(content)
                        save_content = content
                    except json.JSONDecodeError:
                        # 如果解析失败，将字符串作为JSON字符串保存
                        save_content = json.dumps(content, ensure_ascii=False, indent=2)
                else:
                    # 如果是对象或数组，序列化为JSON
                    save_content = json.dumps(content, ensure_ascii=False, indent=2)
            else:
                # 文本模式
                save_content = str(content)
            
            # 异步写入文件
            async with aiofiles.open(path, 'w', encoding=encoding) as f:
                await f.write(save_content)
            
            return ToolCallResult(
                tool_call_id="file_save",
                result=f"文件已成功保存到: {path.absolute()}",
                output={
                    "file_path": str(path.absolute()),
                    "size": len(save_content),
                    "mode": mode,
                    "encoding": encoding
                }
            )
            
        except Exception as e:
            raise ToolError(f"保存文件失败: {str(e)}")


class FileReadTool(BaseTool):
    """
    文件读取工具，专门用于读取具体文件的内容，支持文本和JSON文件。

    注意：此工具只能读取具体的文件内容，不能读取文件夹结构或列出目录内容。
    如需查看文件夹结构，请使用其他相应的目录浏览工具。
    """

    name: str = "file_read"
    description: str = "读取具体文件的内容，支持文本和JSON格式。注意：只能读取文件内容，不能读取文件夹结构或目录列表"
    parameters: dict = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要读取的文件路径（请使用绝对路径或者当前工程下的相对路径））"
            },
            "mode": {
                "type": "string",
                "enum": ["text", "json", "auto"],
                "description": "读取模式：text（文本）、json（JSON格式）或auto（自动检测）",
                "default": "auto"
            },
            "encoding": {
                "type": "string",
                "description": "文件编码格式",
                "default": "utf-8"
            },
            "lines": {
                "type": "object",
                "description": "指定读取的行范围",
                "properties": {
                    "start": {
                        "type": "integer",
                        "description": "起始行号（从1开始）"
                    },
                    "end": {
                        "type": "integer",
                        "description": "结束行号（包含）"
                    }
                }
            },
            "show_line_numbers": {
                "type": "boolean",
                "description": "是否显示行号",
                "default": True
            }
        },
        "required": ["file_path"],
        "additionalProperties": False
    }
    
    async def execute(
        self,
        *,
        file_path: str,
        mode: str = "auto",
        encoding: str = "utf-8",
        lines: Optional[Dict[str, int]] = None,
        show_line_numbers: bool = True,
        **kwargs
    ) -> ToolCallResult:
        """
        执行文件读取操作。

        参数：
        - file_path: 文件路径
        - mode: 读取模式（text、json或auto）
        - encoding: 文件编码
        - lines: 指定读取的行范围
        - show_line_numbers: 是否显示行号
        """
        try:
            # 转换为Path对象
            path = Path(file_path)
            
            # 检查文件是否存在
            if not path.exists():
                raise ToolError(f"文件不存在: {file_path}")
            
            if not path.is_file():
                raise ToolError(f"路径不是文件: {file_path}")
            
            # 异步读取文件
            async with aiofiles.open(path, 'r', encoding=encoding) as f:
                content = await f.read()
            
            # 处理指定行范围
            original_start_line = 1
            if lines:
                all_lines = content.splitlines()
                start = lines.get('start', 1) - 1  # 转换为0索引
                end = lines.get('end', len(all_lines))
                selected_lines = all_lines[start:end]
                original_start_line = lines.get('start', 1)
                content = '\n'.join(selected_lines)
            
            # 根据模式处理内容
            result_content = content
            detected_mode = mode
            
            if mode == "auto":
                # 自动检测模式
                if path.suffix.lower() in ['.json', '.jsonl']:
                    detected_mode = "json"
                else:
                    detected_mode = "text"
            
            if detected_mode == "json":
                try:
                    result_content = json.loads(content)
                except json.JSONDecodeError as e:
                    # JSON解析失败，返回原始文本
                    detected_mode = "text"
                    result_content = content

            # 添加行号（仅对文本模式且启用行号显示时）
            if detected_mode == "text" and show_line_numbers:
                lines_list = content.splitlines()
                numbered_lines = []
                for i, line in enumerate(lines_list, start=original_start_line):
                    numbered_lines.append(f"{i:5}→{line}")
                result_content = '\n'.join(numbered_lines)
            
            return ToolCallResult(
                tool_call_id="file_read",
                result=f"成功读取文件: {result_content}",
                output={
                    "content": result_content,
                    "file_path": str(path.absolute()),
                    "size": len(content),
                    "mode": detected_mode,
                    "encoding": encoding,
                    "lines_read": lines if lines else "all",
                    "show_line_numbers": show_line_numbers
                }
            )
            
        except Exception as e:
            raise ToolError(f"读取文件失败: {str(e)}")


class FileCreateTool(BaseTool):
    """
    文件创建工具，用于创建新文件或确保文件存在。
    """
    
    name: str = "file_create"
    description: str = "创建新文件或确保文件存在，支持创建空文件或带初始内容的文件"
    parameters: dict = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要创建的文件路径（相对或绝对路径）"
            },
            "content": {
                "type": ["string", "object", "array", "null"],
                "description": "文件的初始内容，可选。如果不提供则创建空文件",
                "default": ""
            },
            "mode": {
                "type": "string",
                "enum": ["text", "json"],
                "description": "内容模式：text（文本）或json（JSON格式）",
                "default": "text"
            },
            "encoding": {
                "type": "string",
                "description": "文件编码格式",
                "default": "utf-8"
            },
            "overwrite": {
                "type": "boolean",
                "description": "如果文件已存在是否覆盖",
                "default": False
            },
            "create_dirs": {
                "type": "boolean",
                "description": "如果目录不存在是否自动创建",
                "default": True
            }
        },
        "required": ["file_path"],
        "additionalProperties": False
    }
    
    async def execute(
        self,
        *,
        file_path: str,
        content: Optional[Union[str, Dict, list]] = "",
        mode: str = "text",
        encoding: str = "utf-8",
        overwrite: bool = False,
        create_dirs: bool = True,
        **kwargs
    ) -> ToolCallResult:
        """
        执行文件创建操作。
        
        参数：
        - file_path: 文件路径
        - content: 初始内容（可选）
        - mode: 内容模式（text或json）
        - encoding: 文件编码
        - overwrite: 是否覆盖已存在的文件
        - create_dirs: 是否自动创建目录
        """
        try:
            # 转换为Path对象
            path = Path(file_path)
            
            # 检查文件是否已存在
            if path.exists() and not overwrite:
                return ToolCallResult(
                    tool_call_id="file_create",
                    result=f"文件已存在: {path.absolute()}",
                    output={
                        "file_path": str(path.absolute()),
                        "existed": True,
                        "created": False,
                        "size": path.stat().st_size if path.is_file() else 0
                    }
                )
            
            # 创建目录（如果需要）
            if create_dirs and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            
            # 处理内容
            if content is None:
                save_content = ""
            elif mode == "json" and content != "":
                if isinstance(content, str):
                    # 如果是字符串，尝试验证是否为有效JSON
                    try:
                        json.loads(content)
                        save_content = content
                    except json.JSONDecodeError:
                        # 如果不是有效JSON，将其作为JSON字符串保存
                        save_content = json.dumps(content, ensure_ascii=False, indent=2)
                else:
                    # 如果是对象或数组，序列化为JSON
                    save_content = json.dumps(content, ensure_ascii=False, indent=2)
            else:
                # 文本模式或空内容
                save_content = str(content) if content else ""
            
            # 创建或覆盖文件
            async with aiofiles.open(path, 'w', encoding=encoding) as f:
                await f.write(save_content)
            
            return ToolCallResult(
                tool_call_id="file_create",
                result=f"文件已成功创建: {path.absolute()}",
                output={
                    "file_path": str(path.absolute()),
                    "existed": False,
                    "created": True,
                    "size": len(save_content),
                    "mode": mode,
                    "encoding": encoding,
                    "has_content": bool(save_content)
                }
            )
            
        except Exception as e:
            raise ToolError(f"创建文件失败: {str(e)}")

