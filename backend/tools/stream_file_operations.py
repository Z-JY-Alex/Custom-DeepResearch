
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
import difflib
import re

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
- modify: 流式修改文件指定行范围的内容（支持智能缩进和去重）
- insert: 流式在文件指定位置插入内容（支持智能缩进）

适合用于：
- 生成长文档、文章、报告
- 编写和修改代码文件
- 动态更新配置文件
- 实时编辑文档内容
- 流式替换或插入内容

智能缩进功能（auto_indent=True时）：
- modify模式：自动检测被替换行的缩进级别，并将新内容对齐到相同缩进
- insert模式：自动检测插入位置所在行的缩进级别，并将新内容对齐到相同缩进
- 保持代码格式的一致性，特别适用于修改Python、JavaScript等对缩进敏感的代码

智能去重功能（auto_deduplicate=True时）：
- modify模式：自动检测新内容末尾是否包含原始内容的重复部分
- 比较时会忽略缩进差异，只比较实际内容
- 如果检测到重复，自动移除重复部分，防止内容重复写入
- 特别适用于LLM可能重复生成部分内容的场景

文件差异显示（show_diff=True时）：
- modify和insert操作完成后自动显示修改前后的差异对比
- 支持unified格式（类似git diff）和simple格式（简单摘要）
- 帮助验证修改是否正确，清晰展示变更内容

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
                "description": f"目标文件路径（相对路径）例如: {{session_id}}/test.md",
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
            "auto_indent": {
                "type": "boolean",
                "description": "是否自动处理缩进（用于modify和insert操作，保持与原始行相同的缩进级别）",
                "default": True
            },
            "auto_deduplicate": {
                "type": "boolean",
                "description": "是否自动去除新内容末尾与原始内容重复的部分（用于modify操作，防止LLM重复生成内容）",
                "default": True
            },
            "show_diff": {
                "type": "boolean",
                "description": "是否在操作完成后显示文件差异（用于modify和insert操作）",
                "default": True
            },
            "diff_format": {
                "type": "string",
                "enum": ["unified", "simple"],
                "description": "差异显示格式：'unified'统一格式（类似git diff），'simple'简单摘要",
                "default": "unified"
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

        # 新增功能状态
        self._auto_indent: bool = True
        self._auto_deduplicate: bool = True
        self._show_diff: bool = True
        self._diff_format: str = "unified"
        self._original_content: str = ""  # 保存原始文件内容用于diff

    async def execute(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """执行流式文件操作"""
        filepath = kwargs.get("filepath")
        operation_mode = kwargs.get("operation_mode", "write")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        encoding = kwargs.get("encoding", "utf-8")
        backup = kwargs.get("backup", True)
        create_dirs = kwargs.get("create_dirs", True)
        auto_indent = kwargs.get("auto_indent", True)
        auto_deduplicate = kwargs.get("auto_deduplicate", True)
        show_diff = kwargs.get("show_diff", True)
        diff_format = kwargs.get("diff_format", "unified")
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
                self._auto_indent = auto_indent
                self._auto_deduplicate = auto_deduplicate
                self._show_diff = show_diff
                self._diff_format = diff_format

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

        # 保存原始内容用于diff
        self._original_content = content

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

        # 保存原始内容用于diff
        self._original_content = content

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

        # 获取被替换的原始行内容
        start_idx = self._start_line - 1
        end_idx = self._end_line
        original_replaced_lines = self._original_lines[start_idx:end_idx]

        # 内容验证和警告
        warnings = []
        expected_lines = end_idx - start_idx
        actual_lines = len(new_lines)

        # 检查新内容行数是否与预期差异过大
        if actual_lines < expected_lines * 0.5:
            warnings.append(f"新内容行数({actual_lines})明显少于被替换行数({expected_lines})，请确认是否正确")
        elif actual_lines > expected_lines * 2:
            warnings.append(f"新内容行数({actual_lines})明显多于被替换行数({expected_lines})，请确认是否正确")

        # 智能去重：检测新内容末尾是否包含原始内容的重复
        # 不仅检查被替换的行，还要检查替换范围之后的行（防止LLM生成超出范围的重复）
        removed_duplicates = 0
        if self._auto_deduplicate:
            # 扩展检查范围：包括被替换的行和之后的一些行
            extended_check_lines = self._original_lines[start_idx:]  # 从替换开始位置到文件末尾
            new_lines, removed_duplicates = self._remove_duplicate_suffix(new_lines, extended_check_lines)

        # 再次检查去重后的行数
        if removed_duplicates > 0:
            actual_lines_after_dedup = len(new_lines)
            if actual_lines_after_dedup == 0:
                warnings.append("⚠️  去重后内容为空，可能LLM仅重复生成了原内容")

        # 智能缩进处理
        if self._auto_indent and self._start_line > 0 and new_lines:
            # 获取原始行的缩进
            original_line = self._original_lines[self._start_line - 1]
            base_indent = self._detect_indent(original_line)

            # 应用缩进到新内容
            if base_indent and new_lines:
                new_lines = self._apply_indent_to_lines(new_lines, base_indent)

        modified_lines = self._original_lines.copy()

        # 替换指定行范围
        modified_lines[start_idx:end_idx] = new_lines

        # 写入修改后的内容
        final_content = '\n'.join(modified_lines)
        if final_content and not final_content.endswith('\n'):
            final_content += '\n'

        async with aiofiles.open(self._filepath, 'w', encoding=self._encoding) as f:
            await f.write(final_content)

        # 生成描述
        if self._start_line == self._end_line:
            desc = f"替换第{self._start_line}行"
        else:
            desc = f"替换第{self._start_line}-{self._end_line}行"

        result = f"{desc}，文件已更新"

        # 添加统计信息
        result += f"\n📊 原内容: {expected_lines}行 → 新内容: {len(new_lines)}行"

        # 如果检测到并移除了重复内容，添加提示
        if removed_duplicates > 0:
            result += f"\n⚠️  检测到新内容末尾有{removed_duplicates}行与原内容重复，已自动去重"

        # 添加警告信息
        if warnings:
            result += "\n\n⚠️  警告:\n" + "\n".join(f"  - {w}" for w in warnings)

        # 生成并显示差异
        if self._show_diff:
            diff_output = await self._generate_diff(self._original_content, final_content)
            if diff_output:
                result += f"\n\n{diff_output}"

        return result

    async def _apply_insert(self) -> str:
        """应用插入操作"""
        new_content = ''.join(self._collected_content)
        new_lines = new_content.splitlines() if new_content else []

        # 智能缩进处理
        if self._auto_indent and new_lines:
            base_indent = ""
            # 如果插入位置在现有内容中，获取该行的缩进
            if self._start_line <= len(self._original_lines):
                reference_line = self._original_lines[self._start_line - 1]
                base_indent = self._detect_indent(reference_line)
            # 如果插入在末尾，尝试获取上一行的缩进
            elif len(self._original_lines) > 0:
                reference_line = self._original_lines[-1]
                base_indent = self._detect_indent(reference_line)

            # 应用缩进到新内容
            if base_indent:
                new_lines = self._apply_indent_to_lines(new_lines, base_indent)

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

        result = f"在第{self._start_line}行前插入了{len(new_lines)}行，文件已更新"

        # 生成并显示差异
        if self._show_diff:
            diff_output = await self._generate_diff(self._original_content, final_content)
            if diff_output:
                result += f"\n\n{diff_output}"

        return result

    def _remove_duplicate_suffix(self, new_lines: List[str], original_lines: List[str]) -> tuple[List[str], int]:
        """
        检测并移除新内容末尾与原始内容重复的部分

        Args:
            new_lines: LLM生成的新行内容
            original_lines: 被替换的原始行内容

        Returns:
            (去重后的新行列表, 移除的重复行数)
        """
        if not new_lines or not original_lines:
            return new_lines, 0

        # 从新内容末尾开始，逐步增加匹配长度，寻找最长的重复序列
        max_duplicate_len = 0
        max_check_len = min(len(new_lines), len(original_lines))

        # 从小到大检查不同长度的后缀
        for check_len in range(1, max_check_len + 1):
            new_suffix = new_lines[-check_len:]

            # 检查这个后缀是否在原始内容中存在
            # 不仅检查末尾，也检查原始内容的任意位置
            for i in range(len(original_lines) - check_len + 1):
                original_segment = original_lines[i:i + check_len]

                # 比较时去除首尾空格，因为缩进可能不同
                if self._lines_match_ignoring_indent(new_suffix, original_segment):
                    max_duplicate_len = check_len
                    break

        # 如果找到重复，移除新内容末尾的重复部分
        if max_duplicate_len > 0:
            return new_lines[:-max_duplicate_len], max_duplicate_len

        return new_lines, 0

    def _lines_match_ignoring_indent(self, lines1: List[str], lines2: List[str]) -> bool:
        """
        比较两个行列表是否匹配（忽略缩进差异）

        Args:
            lines1: 第一组行
            lines2: 第二组行

        Returns:
            如果内容匹配则返回True
        """
        if len(lines1) != len(lines2):
            return False

        for l1, l2 in zip(lines1, lines2):
            # 去除首尾空格后比较
            if l1.strip() != l2.strip():
                return False

        return True

    def _detect_indent(self, line: str) -> str:
        """检测行的缩进字符串"""
        match = re.match(r'^(\s*)', line)
        return match.group(1) if match else ""

    def _apply_indent_to_lines(self, lines: List[str], base_indent: str) -> List[str]:
        """将基准缩进应用到多行文本"""
        if not lines:
            return lines

        if not base_indent:
            return lines

        # 首先找到所有非空行的最小缩进（LLM生成内容的基准缩进）
        min_indent = None
        for line in lines:
            if line.strip():  # 非空行
                line_indent = self._detect_indent(line)
                indent_len = len(line_indent)
                if min_indent is None or indent_len < min_indent:
                    min_indent = indent_len

        # 如果所有行都是空行，直接返回
        if min_indent is None:
            return lines

        result = []
        for line in lines:
            if line.strip():  # 非空行
                # 获取当前行的缩进
                current_indent = self._detect_indent(line)
                # 计算相对于最小缩进的额外缩进
                extra_indent_len = len(current_indent) - min_indent
                extra_indent = current_indent[min_indent:] if extra_indent_len > 0 else ""

                # 应用目标基准缩进 + 相对额外缩进
                stripped_line = line.lstrip()
                result.append(base_indent + extra_indent + stripped_line)
            else:  # 空行保持为空行
                result.append(line)

        return result

    async def _generate_diff(self, original_content: str, new_content: str) -> str:
        """生成文件差异对比"""
        if not self._show_diff:
            return ""

        original_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        if self._diff_format == "unified":
            diff = difflib.unified_diff(
                original_lines, new_lines,
                fromfile=f"{self._filepath.name} (原始)",
                tofile=f"{self._filepath.name} (修改后)",
                lineterm='',
                n=3
            )
            diff_text = '\n'.join(diff)
            return self._colorize_diff(diff_text) if diff_text else ""

        elif self._diff_format == "simple":
            return self._generate_simple_diff(original_lines, new_lines)

        return ""

    def _colorize_diff(self, diff_text: str) -> str:
        """为diff添加颜色标记"""
        if not diff_text:
            return diff_text

        lines = diff_text.split('\n')
        colored_lines = []

        for line in lines:
            if line.startswith('+++') or line.startswith('---'):
                colored_lines.append(f"\033[1m{line}\033[0m")  # 粗体
            elif line.startswith('+'):
                colored_lines.append(f"\033[32m{line}\033[0m")  # 绿色
            elif line.startswith('-'):
                colored_lines.append(f"\033[31m{line}\033[0m")  # 红色
            elif line.startswith('@@'):
                colored_lines.append(f"\033[36m{line}\033[0m")  # 青色
            else:
                colored_lines.append(line)

        return '\n'.join(colored_lines)

    def _generate_simple_diff(self, original_lines: List[str], new_lines: List[str]) -> str:
        """生成简单的差异摘要"""
        matcher = difflib.SequenceMatcher(None, original_lines, new_lines)

        changes = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                changes.append(f"  修改: 行 {i1+1}-{i2} → {j1+1}-{j2} ({i2-i1}行变为{j2-j1}行)")
            elif tag == 'delete':
                changes.append(f"  删除: 行 {i1+1}-{i2} ({i2-i1}行)")
            elif tag == 'insert':
                changes.append(f"  插入: 行 {j1+1}-{j2} ({j2-j1}行)")

        if changes:
            ratio = matcher.ratio() * 100
            stats = f"📊 差异统计:\n  相似度: {ratio:.2f}%\n  变更详情:\n" + '\n'.join(changes)
            return stats
        else:
            return ""

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
        self._auto_indent = True
        self._auto_deduplicate = True
        self._show_diff = True
        self._diff_format = "unified"
        self._original_content = ""
    
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