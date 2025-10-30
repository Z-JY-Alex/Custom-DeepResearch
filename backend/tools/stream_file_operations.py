
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import aiofiles
from backend.tools.base import BaseTool


class StreamFileOperationTool(BaseTool):
    """统一的流式文件操作工具 - 支持写入、修改、追加等操作"""

    name: str = "stream_file_operation"
    description: str = """统一的流式文件操作工具，支持多种文件操作模式。

调用此工具后，你后续生成的所有内容都会被自动实时处理到指定文件中。

支持的操作模式：
- write: 流式写入新文件（覆盖模式）
- append: 流式追加到文件末尾
- modify: 流式修改文件指定行范围的内容
- insert: 流式在文件指定位置插入内容

适合用于：
- 生成长文档、文章、报告
- 编写和修改代码文件
- 动态更新配置文件
- 实时编辑文档内容
- 流式替换或插入内容

特殊要求：
- 在写入代码或文档时，不得在内容起始位置或任何位置添加 ```python、```markdown、```json 等语言类型标识符。
- 仅输出文件内容本身，保持文件原生格式。
- 不添加多余的前缀、后缀或格式化符号。

使用方式：
调用此工具指定操作模式和参数，然后直接开始生成内容。
"""

    parameters: dict = {
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "目标文件路径（相对路径）例如: output/test.md",
            },
            "operation_mode": {
                "type": "string",
                "enum": ["write", "append", "modify", "insert"],
                "description": "操作模式：'write'覆盖写入，'append'追加到末尾，'modify'修改指定范围，'insert'在指定位置插入",
                "default": "write"
            },
            "start_line": {
                "type": "integer",
                "description": "开始行号（从1开始）- 用于modify和insert操作",
                "minimum": 1
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号（包含）- 仅用于modify操作，如果不指定则等于start_line",
                "minimum": 1
            },
            "encoding": {
                "type": "string",
                "description": "文件编码格式，默认 utf-8",
                "default": "utf-8"
            },
            "backup": {
                "type": "boolean",
                "description": "是否在修改前创建备份文件（仅用于modify和insert操作）",
                "default": True
            },
            "create_dirs": {
                "type": "boolean",
                "description": "如果目录不存在是否自动创建",
                "default": True
            },
            "status": {
                "type": "string",
                "enum": ["start", "end"],
                "description": "操作状态：'start'表示开始操作，'end'表示操作完成",
            }
        },
        "required": ["filepath", "status"]
    }

    def __init__(self):
        super().__init__()
        # 实例状态管理
        self._is_active: bool = False
        self._operation_mode: str = "write"
        self._filepath: Optional[Path] = None
        self._encoding: str = "utf-8"

        # 写入模式状态
        self._active_file: Any = None
        self._total_bytes: int = 0
        self._chunk_count: int = 0

        # 修改模式状态
        self._original_lines: List[str] = []
        self._start_line: Optional[int] = None
        self._end_line: Optional[int] = None
        self._collected_content: List[str] = []
        self._backup_created: bool = False
        self._backup_path: Optional[Path] = None

    async def execute(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """执行流式文件操作"""
        filepath = kwargs.get("filepath")
        operation_mode = kwargs.get("operation_mode", "write")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        encoding = kwargs.get("encoding", "utf-8")
        backup = kwargs.get("backup", True)
        create_dirs = kwargs.get("create_dirs", True)
        status = kwargs.get("status", "start")

        try:
            if status == "start":
                # 如果之前有活跃操作，先关闭
                if self._is_active:
                    await self._cleanup()

                # 构建完整路径
                full_path = self._get_safe_path(filepath)

                # 根据操作模式初始化
                if operation_mode == "write":
                    yield await self._init_write_mode(full_path, encoding, create_dirs)
                elif operation_mode == "append":
                    yield await self._init_append_mode(full_path, encoding, create_dirs)
                elif operation_mode == "modify":
                    if not start_line:
                        yield "✗ modify操作需要指定start_line"
                        return
                    yield await self._init_modify_mode(full_path, start_line, end_line, encoding, backup)
                elif operation_mode == "insert":
                    if not start_line:
                        yield "✗ insert操作需要指定start_line"
                        return
                    yield await self._init_insert_mode(full_path, start_line, encoding, backup)
                else:
                    yield f"✗ 不支持的操作模式: {operation_mode}"
                    return

                # 设置通用状态
                self._is_active = True
                self._operation_mode = operation_mode
                self._filepath = full_path
                self._encoding = encoding

            elif status == "end":
                # 完成操作
                if self._is_active:
                    result = await self._finalize_operation()
                    yield f"✓ 文件操作完成: {filepath} - {result}"
                else:
                    yield f"✗ 没有活动的文件操作可以完成"

        except Exception as e:
            yield f"✗ 文件操作失败: {str(e)}"
            await self._handle_failure()
    
    async def _init_write_mode(self, full_path: Path, encoding: str, create_dirs: bool) -> str:
        """初始化写入模式"""
        if create_dirs:
            full_path.parent.mkdir(parents=True, exist_ok=True)

        self._active_file = await aiofiles.open(full_path, mode='w', encoding=encoding)
        self._total_bytes = 0
        self._chunk_count = 0

        return f"✓ 写入模式已准备就绪: {full_path.name} (覆盖写入)"

    async def _init_append_mode(self, full_path: Path, encoding: str, create_dirs: bool) -> str:
        """初始化追加模式"""
        if create_dirs:
            full_path.parent.mkdir(parents=True, exist_ok=True)

        # 如果文件不存在，创建空文件
        if not full_path.exists():
            full_path.touch()

        # 检查文件是否为空，如果不为空且不以换行符结尾，添加换行符
        if full_path.stat().st_size > 0:
            async with aiofiles.open(full_path, 'r', encoding=encoding) as f:
                content = await f.read()
                if content and not content.endswith('\n'):
                    async with aiofiles.open(full_path, 'a', encoding=encoding) as f:
                        await f.write('\n')

        self._active_file = await aiofiles.open(full_path, mode='a', encoding=encoding)
        self._total_bytes = 0
        self._chunk_count = 0

        return f"✓ 追加模式已准备就绪: {full_path.name} (追加到末尾)"

    async def _init_modify_mode(self, full_path: Path, start_line: int, end_line: Optional[int],
                              encoding: str, backup: bool) -> str:
        """初始化修改模式"""
        if not full_path.exists():
            return f"✗ 文件不存在: {full_path}"

        # 读取原文件内容
        async with aiofiles.open(full_path, 'r', encoding=encoding) as f:
            content = await f.read()

        self._original_lines = content.splitlines()
        original_line_count = len(self._original_lines)

        # 验证行号范围
        if start_line < 1 or start_line > original_line_count:
            return f"✗ start_line超出范围: {start_line}（文件共{original_line_count}行）"

        if end_line is None:
            end_line = start_line

        if end_line < start_line or end_line > original_line_count:
            return f"✗ end_line无效: {end_line}（应在{start_line}-{original_line_count}之间）"

        # 创建备份
        if backup and content:
            backup_path = full_path.with_suffix(full_path.suffix + '.backup')
            async with aiofiles.open(backup_path, 'w', encoding=encoding) as f:
                await f.write(content)
            self._backup_created = True
            self._backup_path = backup_path

        # 设置状态
        self._start_line = start_line
        self._end_line = end_line
        self._collected_content = []

        if start_line == end_line:
            desc = f"替换第{start_line}行"
        else:
            desc = f"替换第{start_line}-{end_line}行"

        return f"✓ 修改模式已准备就绪: {full_path.name} ({desc})"

    async def _init_insert_mode(self, full_path: Path, start_line: int, encoding: str, backup: bool) -> str:
        """初始化插入模式"""
        if not full_path.exists():
            return f"✗ 文件不存在: {full_path}"

        # 读取原文件内容
        async with aiofiles.open(full_path, 'r', encoding=encoding) as f:
            content = await f.read()

        self._original_lines = content.splitlines()
        original_line_count = len(self._original_lines)

        # 验证插入位置
        if start_line < 1 or start_line > original_line_count + 1:
            return f"✗ 插入位置超出范围: {start_line}（可插入位置: 1-{original_line_count + 1}）"

        # 创建备份
        if backup and content:
            backup_path = full_path.with_suffix(full_path.suffix + '.backup')
            async with aiofiles.open(backup_path, 'w', encoding=encoding) as f:
                await f.write(content)
            self._backup_created = True
            self._backup_path = backup_path

        # 设置状态
        self._start_line = start_line
        self._collected_content = []

        return f"✓ 插入模式已准备就绪: {full_path.name} (在第{start_line}行前插入)"
    
    async def write_chunk(self, chunk: str) -> Any:
        """
        处理内容块（由框架调用）
        """
        if not self._is_active:
            return "文件操作未激活"
        
        try:
            chunk_content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            
            if self._operation_mode in ["write", "append"]:
                # 直接写入模式
                await self._active_file.write(chunk_content)
                await self._active_file.flush()
                
                chunk_size = len(chunk_content.encode(self._encoding))
                self._total_bytes += chunk_size
                self._chunk_count += 1
                
                return self._chunk_count
                
            elif self._operation_mode in ["modify", "insert"]:
                # 修改/插入模式 - 收集内容
                self._collected_content.append(chunk_content)
                return f"已收集内容块 {len(self._collected_content)}"

        except Exception as e:
            await self._handle_failure()
            return f"ERROR: {str(e)}"
    
    async def _finalize_operation(self) -> str:
        """完成文件操作"""
        try:
            if self._operation_mode in ["write", "append"]:
                # 直接写入模式 - 关闭文件
                if self._active_file:
                    await self._active_file.close()

                # 确保文件以换行符结尾（如果内容不为空）
                if self._filepath and self._filepath.exists() and self._filepath.stat().st_size > 0:
                    async with aiofiles.open(self._filepath, 'r+', encoding=self._encoding) as f:
                        content = await f.read()
                        if content and not content.endswith('\n'):
                            await f.write('\n')

                file_size = self._filepath.stat().st_size if self._filepath else 0
                result = f"文件保存成功: {self._filepath.name}，大小: {file_size} 字节"

            elif self._operation_mode == "modify":
                # 修改模式 - 应用修改
                result = await self._apply_modify()

            elif self._operation_mode == "insert":
                # 插入模式 - 在指定位置插入
                result = await self._apply_insert()

            # 操作成功，清理备份文件
            await self._cleanup_backup()
            return result

        except Exception as e:
            # 操作失败，执行回滚
            await self._handle_failure()
            return f"ERROR: {str(e)}"
        finally:
            await self._cleanup()
    
    async def _apply_modify(self) -> str:
        """应用修改操作"""
        new_content = ''.join(self._collected_content)
        new_lines = new_content.splitlines() if new_content.strip() else []

        modified_lines = self._original_lines.copy()

        # 替换指定行范围
        start_idx = self._start_line - 1
        end_idx = self._end_line
        modified_lines[start_idx:end_idx] = new_lines

        # 写入修改后的内容
        final_content = '\n'.join(modified_lines)
        if final_content and not final_content.endswith('\n'):
            final_content += '\n'

        async with aiofiles.open(self._filepath, 'w', encoding=self._encoding) as f:
            await f.write(final_content)

        if self._start_line == self._end_line:
            desc = f"替换第{self._start_line}行"
        else:
            desc = f"替换第{self._start_line}-{self._end_line}行"

        return f"{desc}，文件已更新"

    async def _apply_insert(self) -> str:
        """应用插入操作"""
        new_content = ''.join(self._collected_content)
        new_lines = new_content.splitlines() if new_content else []

        modified_lines = self._original_lines.copy()

        # 在指定位置插入
        insert_idx = self._start_line - 1
        modified_lines[insert_idx:insert_idx] = new_lines

        # 写入修改后的内容
        final_content = '\n'.join(modified_lines)
        if final_content and not final_content.endswith('\n'):
            final_content += '\n'

        async with aiofiles.open(self._filepath, 'w', encoding=self._encoding) as f:
            await f.write(final_content)

        return f"在第{self._start_line}行前插入了{len(new_lines)}行，文件已更新"

    async def _handle_failure(self):
        """处理操作失败，执行回滚"""
        try:
            # 如果创建了备份且有失败，尝试恢复原文件
            if self._backup_created and self._backup_path and self._backup_path.exists():
                if self._filepath and self._filepath.exists():
                    # 恢复原文件
                    async with aiofiles.open(self._backup_path, 'r', encoding=self._encoding) as backup_f:
                        backup_content = await backup_f.read()
                    async with aiofiles.open(self._filepath, 'w', encoding=self._encoding) as target_f:
                        await target_f.write(backup_content)

                # 删除备份文件
                self._backup_path.unlink(missing_ok=True)
        except Exception:
            # 如果回滚失败，至少尝试删除备份文件
            if self._backup_path and self._backup_path.exists():
                try:
                    self._backup_path.unlink()
                except Exception:
                    pass
        finally:
            await self._cleanup()

    async def _cleanup_backup(self):
        """清理备份文件（操作成功后）"""
        try:
            if self._backup_created and self._backup_path and self._backup_path.exists():
                self._backup_path.unlink()
        except Exception:
            # 即使删除备份文件失败也不影响主操作
            pass
    
    async def _cleanup(self):
        """清理状态"""
        try:
            # 关闭活跃文件
            if self._active_file:
                await self._active_file.close()
        except:
            pass

        # 重置所有状态
        self._is_active = False
        self._operation_mode = "write"
        self._filepath = None
        self._active_file = None
        self._total_bytes = 0
        self._chunk_count = 0
        self._original_lines = []
        self._start_line = None
        self._end_line = None
        self._collected_content = []
        self._backup_created = False
        self._backup_path = None
    
    def is_active(self) -> bool:
        """检查是否有活跃的文件操作"""
        return self._is_active
    
    def get_operation_mode(self) -> str:
        """获取当前操作模式"""
        return self._operation_mode
    
    def _get_safe_path(self, filepath: str) -> Path:
        """获取安全的文件路径，防止路径遍历攻击"""
        base_dir = Path(".").resolve()

        # 规范化路径
        clean_path = Path(filepath).as_posix()

        # 检查是否包含危险字符
        if ".." in clean_path or clean_path.startswith("/"):
            raise ValueError("不允许的文件路径")

        # 构建相对于base_dir的完整路径
        full_path = (base_dir / clean_path).resolve()

        # 确保路径在base_dir内
        try:
            full_path.relative_to(base_dir.resolve())
        except ValueError:
            raise ValueError("文件路径必须在基础目录内")

        return full_path


# 为了保持向后兼容性，提供别名
StreamFileSaveTool = StreamFileOperationTool
StreamFileModifyTool = StreamFileOperationTool