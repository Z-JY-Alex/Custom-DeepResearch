
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
import difflib
from datetime import datetime

import aiofiles
from backend.tools.base import BaseTool


class FileDiffTool(BaseTool):
    """文件差异比较工具 - 支持多种diff格式和比较模式"""

    name: str = "file_diff"
    description: str = """文件差异比较工具，用于比较两个文件或同一文件的不同版本。

支持的比较格式：
- unified: 统一差异格式（类似 git diff）
- context: 上下文差异格式
- ndiff: 详细的逐行差异
- html: HTML格式的并排比较
- simple: 简单的差异统计

支持的比较模式：
- files: 比较两个不同的文件
- backup: 比较文件与其备份版本
- content: 比较文件与提供的文本内容

适合用于：
- 查看文件修改前后的差异
- 比较配置文件的变化
- 代码审查和版本对比
- 验证文件修改是否正确

使用方式：
指定要比较的文件路径和比较格式，工具会返回详细的差异信息。
"""

    parameters: dict = {
        "type": "object",
        "properties": {
            "source_file": {
                "type": "string",
                "description": "源文件路径（相对路径）",
            },
            "target_file": {
                "type": "string",
                "description": "目标文件路径（相对路径）- 用于files模式",
            },
            "compare_mode": {
                "type": "string",
                "enum": ["files", "backup", "content"],
                "description": "比较模式：'files'比较两个文件，'backup'比较文件与备份，'content'比较文件与提供的内容",
                "default": "files"
            },
            "diff_format": {
                "type": "string",
                "enum": ["unified", "context", "ndiff", "html", "simple"],
                "description": "差异格式：'unified'统一格式，'context'上下文格式，'ndiff'详细差异，'html'网页格式，'simple'简单统计",
                "default": "unified"
            },
            "context_lines": {
                "type": "integer",
                "description": "上下文行数（用于unified和context格式），默认3",
                "default": 3,
                "minimum": 0
            },
            "ignore_whitespace": {
                "type": "boolean",
                "description": "是否忽略空白字符的差异",
                "default": False
            },
            "ignore_case": {
                "type": "boolean",
                "description": "是否忽略大小写",
                "default": False
            },
            "content": {
                "type": "string",
                "description": "用于content模式的比较内容",
            },
            "encoding": {
                "type": "string",
                "description": "文件编码格式，默认 utf-8",
                "default": "utf-8"
            },
            "show_stats": {
                "type": "boolean",
                "description": "是否显示差异统计信息",
                "default": True
            }
        },
        "required": ["source_file"]
    }

    def __init__(self):
        super().__init__()

    async def execute(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """执行文件差异比较"""
        source_file = kwargs.get("source_file")
        target_file = kwargs.get("target_file")
        compare_mode = kwargs.get("compare_mode", "files")
        diff_format = kwargs.get("diff_format", "unified")
        context_lines = kwargs.get("context_lines", 3)
        ignore_whitespace = kwargs.get("ignore_whitespace", False)
        ignore_case = kwargs.get("ignore_case", False)
        content = kwargs.get("content")
        encoding = kwargs.get("encoding", "utf-8")
        show_stats = kwargs.get("show_stats", True)

        try:
            # 构建源文件路径
            source_path = self._get_safe_path(source_file)
            if not source_path.exists():
                yield f"✗ 源文件不存在: {source_file}"
                return

            # 读取源文件内容
            async with aiofiles.open(source_path, 'r', encoding=encoding) as f:
                source_content = await f.read()

            # 根据比较模式获取目标内容
            if compare_mode == "files":
                if not target_file:
                    yield "✗ files模式需要指定target_file"
                    return
                target_path = self._get_safe_path(target_file)
                if not target_path.exists():
                    yield f"✗ 目标文件不存在: {target_file}"
                    return
                async with aiofiles.open(target_path, 'r', encoding=encoding) as f:
                    target_content = await f.read()
                target_label = target_file

            elif compare_mode == "backup":
                backup_path = source_path.with_suffix(source_path.suffix + '.backup')
                if not backup_path.exists():
                    yield f"✗ 备份文件不存在: {backup_path}"
                    return
                async with aiofiles.open(backup_path, 'r', encoding=encoding) as f:
                    target_content = await f.read()
                target_label = f"{source_file}.backup"

            elif compare_mode == "content":
                if content is None:
                    yield "✗ content模式需要提供content参数"
                    return
                target_content = content
                target_label = "<provided content>"

            else:
                yield f"✗ 不支持的比较模式: {compare_mode}"
                return

            # 预处理内容
            source_lines = source_content.splitlines(keepends=True)
            target_lines = target_content.splitlines(keepends=True)

            if ignore_whitespace:
                source_lines = [line.strip() + '\n' if line.strip() else '\n' for line in source_lines]
                target_lines = [line.strip() + '\n' if line.strip() else '\n' for line in target_lines]

            if ignore_case:
                source_lines = [line.lower() for line in source_lines]
                target_lines = [line.lower() for line in target_lines]

            # 生成差异
            diff_result = await self._generate_diff(
                source_lines, target_lines,
                source_file, target_label,
                diff_format, context_lines
            )

            # 计算统计信息
            if show_stats:
                stats = self._calculate_stats(source_lines, target_lines)
                yield f"\n📊 差异统计:\n{stats}\n"

            # 输出差异内容
            if diff_result:
                yield f"\n{diff_result}"
            else:
                yield "\n✓ 文件内容完全相同，没有差异"

        except Exception as e:
            yield f"✗ 文件比较失败: {str(e)}"

    async def _generate_diff(
        self,
        source_lines: List[str],
        target_lines: List[str],
        source_label: str,
        target_label: str,
        diff_format: str,
        context_lines: int
    ) -> str:
        """生成差异内容"""

        if diff_format == "unified":
            diff = difflib.unified_diff(
                source_lines, target_lines,
                fromfile=source_label,
                tofile=target_label,
                lineterm='',
                n=context_lines
            )
            result = '\n'.join(diff)
            return self._colorize_unified_diff(result) if result else ""

        elif diff_format == "context":
            diff = difflib.context_diff(
                source_lines, target_lines,
                fromfile=source_label,
                tofile=target_label,
                lineterm='',
                n=context_lines
            )
            return '\n'.join(diff)

        elif diff_format == "ndiff":
            diff = difflib.ndiff(source_lines, target_lines)
            return ''.join(diff)

        elif diff_format == "html":
            differ = difflib.HtmlDiff()
            return differ.make_file(
                source_lines, target_lines,
                fromdesc=source_label,
                todesc=target_label
            )

        elif diff_format == "simple":
            return self._generate_simple_diff(source_lines, target_lines)

        return ""

    def _colorize_unified_diff(self, diff_text: str) -> str:
        """为unified diff添加颜色标记（使用ANSI转义码）"""
        if not diff_text:
            return diff_text

        lines = diff_text.split('\n')
        colored_lines = []

        for line in lines:
            if line.startswith('+++') or line.startswith('---'):
                # 文件头 - 粗体
                colored_lines.append(f"\033[1m{line}\033[0m")
            elif line.startswith('+'):
                # 添加的行 - 绿色
                colored_lines.append(f"\033[32m{line}\033[0m")
            elif line.startswith('-'):
                # 删除的行 - 红色
                colored_lines.append(f"\033[31m{line}\033[0m")
            elif line.startswith('@@'):
                # 位置标记 - 青色
                colored_lines.append(f"\033[36m{line}\033[0m")
            else:
                colored_lines.append(line)

        return '\n'.join(colored_lines)

    def _generate_simple_diff(self, source_lines: List[str], target_lines: List[str]) -> str:
        """生成简单的差异摘要"""
        matcher = difflib.SequenceMatcher(None, source_lines, target_lines)

        changes = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                changes.append(f"  修改: 行 {i1+1}-{i2} → {j1+1}-{j2} ({i2-i1}行变为{j2-j1}行)")
            elif tag == 'delete':
                changes.append(f"  删除: 行 {i1+1}-{i2} ({i2-i1}行)")
            elif tag == 'insert':
                changes.append(f"  插入: 行 {j1+1}-{j2} ({j2-j1}行)")

        if changes:
            return "变更详情:\n" + '\n'.join(changes)
        else:
            return "没有差异"

    def _calculate_stats(self, source_lines: List[str], target_lines: List[str]) -> str:
        """计算差异统计信息"""
        matcher = difflib.SequenceMatcher(None, source_lines, target_lines)

        added = 0
        deleted = 0
        modified = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                modified += max(i2 - i1, j2 - j1)
            elif tag == 'delete':
                deleted += i2 - i1
            elif tag == 'insert':
                added += j2 - j1

        ratio = matcher.ratio() * 100

        stats = [
            f"  源文件: {len(source_lines)} 行",
            f"  目标文件: {len(target_lines)} 行",
            f"  相似度: {ratio:.2f}%",
            f"  添加: {added} 行",
            f"  删除: {deleted} 行",
            f"  修改: {modified} 行"
        ]

        return '\n'.join(stats)

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
