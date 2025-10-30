from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import aiofiles
from traitlets import Bool
from backend.tools.base import BaseTool


class StreamFileSaveTool(BaseTool):
    """支持流式写入的文件保存工具 - 单例模式，全局捕获"""
    
    name: str = "stream_file_save"
    description: str = """流式保存文件内容到指定路径。
    
调用此工具后，你后续生成的所有内容都会被自动实时写入到指定文件中。

适合用于：
- 生成长文档、文章、报告  
- 编写代码文件
- 创作故事、小说
- 生成配置文件、数据文件

使用方式：调用此工具指定文件路径，然后直接开始生成要保存的内容。"""
    
    parameters: dict = {
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "要保存的文件路径（相对路径）例如: output/test.md",
            },
            "mode": {
                "type": "string",
                "enum": ["w", "a"],
                "description": "写入模式：'w'为覆盖写入（默认），'a'为追加写入",
                "default": "w"
            },
            "encoding": {
                "type": "string",
                "description": "文件编码格式，默认 utf-8",
                "default": "utf-8"
            },
            "status": {
                "type": "string",
                "enum": ["start", "end"],
                "description": "文件写入操作状态：'start'表示开始写入，'end'表示写入完成",
            }
        },
        "required": ["filepath", "status"]
    }
    base_dir: Path = Path("./output")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    # 全局状态：用于跨调用保存文件句柄
    _active_file: Any = None
    _active_filepath: Any = None
    _total_bytes: int = 0
    _chunk_count: int  = 0
    _is_active: Bool = False
    _encoding: str = "utf-8"

    
    async def execute(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行流式文件保存
        
        这个方法会打开文件并设置为激活状态
        框架需要在后续生成内容时调用 write_chunk() 方法
        """
        filepath = kwargs.get("filepath")
        mode = kwargs.get("mode", "w")
        encoding = kwargs.get("encoding", "utf-8")
        status = kwargs.get("status", "start")
        
        try:
            # 根据状态处理不同的操作
            if status == "start":
                # 如果之前有打开的文件，先关闭
                if self._is_active and self._active_file:
                    await self._active_file.close()
                
                # 构建完整路径
                full_path = self._get_safe_path(filepath)
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 打开文件
                self._active_file = await aiofiles.open(full_path, mode=mode, encoding=encoding)
                self._active_filepath = full_path
                self._encoding = encoding
                self._total_bytes = 0
                self._chunk_count = 0
                self._is_active = True
                
                # 返回准备就绪状态
                yield f"✓ 文件已准备就绪: {filepath} (状态: 开始写入)"
                
            elif status == "end":
                # 完成写入操作
                if self._is_active and self._active_file:
                    result = await self.finalize()
                    yield f"✓ 文件写入完成: {filepath} (状态: 写入完成) - {result}"
                else:
                    yield f"✗ 没有活动的文件写入操作可以完成"
            
        except Exception as e:
            yield f"✗ 文件操作失败: {str(e)}"
            self._is_active = False
    
    async def write_chunk(self, chunk: str) -> Dict[str, Any]:
        """
        写入一个内容块（由框架在生成内容时调用）
        
        Args:
            chunk: 要写入的内容块
            
        Returns:
            写入状态
        """
        if not self._is_active or not self._active_file:
            return "文件保存未激活"
        
        try:
            chunk = chunk.content
            await self._active_file.write(chunk)
            await self._active_file.flush()
            
            chunk_size = len(chunk.encode(self._encoding))
            self._total_bytes += chunk_size
            self._chunk_count += 1
            
            return self._chunk_count
                
        except Exception as e:
            return f"ERROR:{str(e)}"
    
    async def finalize(self) -> Dict[str, Any]:
        """
        完成文件保存（由框架在生成结束时调用）
        
        Returns:
            完成状态和统计信息
        """
        if not self._is_active:
            return "没有活动的文件保存"
        
        try:
            # 关闭文件
            if self._active_file:
                await self._active_file.close()
            
            # 获取文件信息
            file_size = self._active_filepath.stat().st_size if self._active_filepath else 0
            filepath = str(self._active_filepath) if self._active_filepath else "unknown"
            
            result = f"✓ 文件保存成功: {self._active_filepath.name if self._active_filepath else 'unknown'}",
                
            
            # 重置状态
            self._active_file = None
            self._active_filepath = None
            self._is_active = False
            self._total_bytes = 0
            self._chunk_count = 0
            
            return result
            
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def is_active(self) -> bool:
        """检查文件保存是否处于活动状态"""
        return self._is_active
    
    def _get_safe_path(self, filepath: str) -> Path:
        """获取安全的文件路径，防止路径遍历攻击"""
        safe_path = Path(filepath).as_posix()
        if ".." in safe_path or safe_path.startswith("/"):
            raise ValueError("不允许的文件路径")
        full_path = Path(safe_path).resolve()
        if not str(full_path).startswith(str(self.base_dir.resolve())):
            raise ValueError("文件路径必须在基础目录内")
        return full_path


class StreamFileModifyTool(BaseTool):
    """支持流式修改文件内容的工具 - 在现有文件基础上进行修改"""
    
    name: str = "stream_file_modify"
    description: str = """流式修改文件指定行的内容。
    
调用此工具后，你后续生成的所有内容都会被自动实时替换到指定的文件行中。

适合用于：
- 流式修改代码文件中的特定函数或类
- 动态更新配置文件的特定部分
- 实时编辑文档的特定段落
- 流式替换日志文件的某些行

使用方式：调用此工具指定文件路径和修改位置，然后直接开始生成要替换的内容。"""
    
    parameters: dict = {
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "要修改的文件路径（相对路径）",
            },
            "operation": {
                "type": "string",
                "enum": ["replace", "insert", "append"],
                "description": "修改操作类型：'replace'替换指定行，'insert'在指定行前插入，'append'在文件末尾追加",
                "default": "replace"
            },
            "line_number": {
                "type": "integer",
                "description": "操作的起始行号（从1开始）。对于replace和insert操作必须指定",
                "minimum": 1
            },
            "line_count": {
                "type": "integer",
                "description": "要替换的行数（仅用于replace操作），默认为1",
                "minimum": 1,
                "default": 1
            },
            "encoding": {
                "type": "string",
                "description": "文件编码格式，默认 utf-8",
                "default": "utf-8"
            },
            "backup": {
                "type": "boolean",
                "description": "是否在修改前创建备份文件",
                "default": True
            },
            "status": {
                "type": "string",
                "enum": ["start", "end"],
                "description": "修改操作状态：'start'表示开始修改，'end'表示修改完成",
            }
        },
        "required": ["filepath", "status"]
    }
    base_dir: Path = Path("./output")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    # 全局状态：用于跨调用保存修改信息
    _modify_active: bool = False
    _original_lines: List[str] = []
    _modify_filepath: Optional[Path] = None
    _modify_operation: str = "replace"
    _modify_line_number: int = 1
    _modify_line_count: int = 1
    _modify_encoding: str = "utf-8"
    _collected_content: List[str] = []
    _backup_created: bool = False

    async def execute(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行流式文件修改
        
        这个方法会准备文件修改环境并设置为激活状态
        框架需要在后续生成内容时调用 write_chunk() 方法
        """
        filepath = kwargs.get("filepath")
        operation = kwargs.get("operation", "replace")
        line_number = kwargs.get("line_number")
        line_count = kwargs.get("line_count", 1)
        encoding = kwargs.get("encoding", "utf-8")
        backup = kwargs.get("backup", True)
        status = kwargs.get("status", "start")
        
        try:
            if status == "start":
                # 构建完整路径
                full_path = self._get_safe_path(filepath)
                
                if not full_path.exists():
                    yield f"✗ 文件不存在: {filepath}"
                    return
                
                # 读取原文件内容
                async with aiofiles.open(full_path, 'r', encoding=encoding) as f:
                    content = await f.read()
                
                self._original_lines = content.splitlines()
                original_line_count = len(self._original_lines)
                
                # 验证行号
                if operation in ["replace", "insert"] and line_number is None:
                    yield f"✗ {operation}操作需要指定line_number"
                    return
                
                if line_number and (line_number < 1 or line_number > original_line_count + 1):
                    yield f"✗ 行号超出范围: {line_number}（文件共{original_line_count}行）"
                    return
                
                if operation == "replace" and line_number + line_count - 1 > original_line_count:
                    yield f"✗ 替换范围超出文件行数: {line_number}到{line_number + line_count - 1}（文件共{original_line_count}行）"
                    return
                
                # 创建备份
                if backup:
                    backup_path = full_path.with_suffix(full_path.suffix + '.backup')
                    async with aiofiles.open(backup_path, 'w', encoding=encoding) as f:
                        await f.write(content)
                    self._backup_created = True
                
                # 设置修改状态
                self._modify_active = True
                self._modify_filepath = full_path
                self._modify_operation = operation
                self._modify_line_number = line_number or len(self._original_lines) + 1
                self._modify_line_count = line_count
                self._modify_encoding = encoding
                self._collected_content = []
                
                # 返回准备就绪状态
                operation_desc = {
                    "replace": f"替换第{self._modify_line_number}行开始的{line_count}行",
                    "insert": f"在第{self._modify_line_number}行前插入内容",
                    "append": "在文件末尾追加内容"
                }
                
                yield f"✓ 文件修改已准备就绪: {filepath} ({operation_desc.get(operation, operation)})"
                
            elif status == "end":
                # 完成修改操作
                if self._modify_active:
                    result = await self.finalize_modify()
                    yield f"✓ 文件修改完成: {filepath} - {result}"
                else:
                    yield f"✗ 没有活动的文件修改操作可以完成"
                    
        except Exception as e:
            yield f"✗ 文件修改操作失败: {str(e)}"
            self._modify_active = False
    
    async def write_chunk(self, chunk: str) -> Dict[str, Any]:
        """
        收集修改内容块（由框架在生成内容时调用）
        
        Args:
            chunk: 要写入的内容块
            
        Returns:
            收集状态
        """
        if not self._modify_active:
            return "文件修改未激活"
        
        try:
            # 收集内容块
            chunk_content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            self._collected_content.append(chunk_content)
            
            return f"已收集内容块 {len(self._collected_content)}"
                
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    async def finalize_modify(self) -> str:
        """
        完成文件修改（由框架在生成结束时调用）
        
        Returns:
            修改结果信息
        """
        if not self._modify_active:
            return "没有活动的文件修改"
        
        try:
            # 合并收集的内容
            new_content = ''.join(self._collected_content)
            new_lines = new_content.splitlines() if new_content else []
            
            # 根据操作类型修改文件
            modified_lines = self._original_lines.copy()
            
            if self._modify_operation == "replace":
                # 替换指定行
                start_idx = self._modify_line_number - 1
                end_idx = start_idx + self._modify_line_count
                modified_lines[start_idx:end_idx] = new_lines
                operation_desc = f"替换了第{self._modify_line_number}行开始的{self._modify_line_count}行"
                
            elif self._modify_operation == "insert":
                # 在指定行前插入
                insert_idx = self._modify_line_number - 1
                modified_lines[insert_idx:insert_idx] = new_lines
                operation_desc = f"在第{self._modify_line_number}行前插入了{len(new_lines)}行"
                
            elif self._modify_operation == "append":
                # 在文件末尾追加
                modified_lines.extend(new_lines)
                operation_desc = f"在文件末尾追加了{len(new_lines)}行"
            
            # 写入修改后的内容
            final_content = '\n'.join(modified_lines)
            async with aiofiles.open(self._modify_filepath, 'w', encoding=self._modify_encoding) as f:
                await f.write(final_content)
            
            result = f"✓ {operation_desc}，文件已更新"
            
            # 重置状态
            self._modify_active = False
            self._original_lines = []
            self._modify_filepath = None
            self._collected_content = []
            
            return result
            
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def is_modify_active(self) -> bool:
        """检查文件修改是否处于活动状态"""
        return self._modify_active

    def _get_safe_path(self, filepath: str) -> Path:
        """获取安全的文件路径，防止路径遍历攻击"""
        safe_path = Path(filepath).as_posix()
        if ".." in safe_path or safe_path.startswith("/"):
            raise ValueError("不允许的文件路径")
        full_path = Path(safe_path).resolve()
        if not str(full_path).startswith(str(self.base_dir.resolve())):
            raise ValueError("文件路径必须在基础目录内")
        return full_path