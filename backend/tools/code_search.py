"""
代码搜索工具：支持自然语言查询，在代码库中查找相关代码片段
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import asyncio
import aiofiles

from backend.tools.base import BaseTool, ToolError, ToolCallResult
from loguru import logger


class CodeSearchTool(BaseTool):
    """
    代码搜索工具：通过自然语言查询在代码库中查找相关代码
    
    支持功能：
    - 自然语言语义搜索
    - 关键词匹配
    - 文件路径过滤
    - 代码片段提取
    - 相关性评分
    """
    
    name: str = "code_search"
    description: str = (
        "在代码库中搜索与查询相关的代码片段。"
        "支持自然语言查询，会返回匹配的文件路径、代码片段和行号。"
        "适用于查找功能实现、API调用、组件定义等。"
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询，使用自然语言描述要查找的代码功能，例如：'How does user login work?', 'Where is the API endpoint for authentication?', 'How is file upload implemented?'"
            },
            "target_directories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "限制搜索范围的目录路径列表（可选）。如果为空，则搜索整个代码库",
                "default": []
            },
            "file_extensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要搜索的文件扩展名列表，例如：['.py', '.js', '.ts']。如果为空，则搜索所有代码文件",
                "default": []
            },
            "max_results": {
                "type": "integer",
                "description": "返回的最大结果数量",
                "default": 10,
                "minimum": 1,
                "maximum": 50
            },
            "min_score": {
                "type": "number",
                "description": "最小相关性分数阈值（0-1），低于此分数的结果将被过滤",
                "default": 0.3,
                "minimum": 0,
                "maximum": 1
            }
        },
        "required": ["query"],
        "additionalProperties": False
    }
    
    # 默认代码文件扩展名
    DEFAULT_CODE_EXTENSIONS = [
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
        '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala', '.sh',
        '.vue', '.html', '.css', '.scss', '.less', '.json', '.yaml', '.yml',
        '.md', '.sql', '.xml', '.toml', '.ini', '.conf'
    ]
    
    # 忽略的目录和文件
    IGNORE_PATTERNS = [
        '__pycache__', '.git', '.svn', '.hg', 'node_modules', '.venv', 'venv',
        'env', '.env', 'dist', 'build', '.pytest_cache', '.mypy_cache',
        '.idea', '.vscode', '.vs', '*.pyc', '*.pyo', '*.pyd', '.DS_Store'
    ]
    
    def __init__(self, work_dir: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.work_dir = Path(work_dir) if work_dir else Path.cwd()
        logger.info(f"CodeSearchTool initialized with work_dir: {self.work_dir}")
    
    async def execute(
        self,
        *,
        query: str,
        target_directories: Optional[List[str]] = None,
        file_extensions: Optional[List[str]] = None,
        max_results: int = 10,
        min_score: float = 0.3,
        **kwargs
    ) -> ToolCallResult:
        """
        执行代码搜索
        
        参数：
        - query: 搜索查询（自然语言）
        - target_directories: 目标目录列表
        - file_extensions: 文件扩展名列表
        - max_results: 最大结果数
        - min_score: 最小相关性分数
        """
        try:
            if not query or not query.strip():
                raise ToolError("搜索查询不能为空")
            
            # 设置默认值
            target_dirs = target_directories or []
            extensions = file_extensions or self.DEFAULT_CODE_EXTENSIONS
            
            # 解析查询，提取关键词
            keywords = self._extract_keywords(query)
            logger.info(f"Search query: {query}, Keywords: {keywords}")
            
            # 确定搜索目录
            search_dirs = self._get_search_directories(target_dirs)
            logger.info(f"Search directories: {[str(d) for d in search_dirs]}")
            
            # 收集所有要搜索的文件
            files_to_search = await self._collect_files(search_dirs, extensions)
            logger.info(f"Found {len(files_to_search)} files to search")
            
            if not files_to_search:
                return ToolCallResult(
                    tool_call_id="code_search",
                    result="未找到可搜索的文件",
                    user_result="未找到匹配的文件",
                    output={"results": [], "query": query, "total_files": 0}
                )
            
            # 并行搜索所有文件
            results = await self._search_files(files_to_search, query, keywords, min_score)
            
            # 按相关性分数排序
            results.sort(key=lambda x: x['score'], reverse=True)
            
            # 限制结果数量
            results = results[:max_results]
            
            # 格式化结果
            formatted_results = self._format_results(results)
            
            # 生成用户友好的结果摘要
            user_result = self._generate_user_summary(formatted_results, query)
            
            return ToolCallResult(
                tool_call_id="code_search",
                result=f"找到 {len(results)} 个相关代码片段",
                user_result=user_result,
                output={
                    "results": formatted_results,
                    "query": query,
                    "total_files_searched": len(files_to_search),
                    "total_results": len(results)
                }
            )
            
        except Exception as e:
            logger.error(f"代码搜索失败: {str(e)}")
            raise ToolError(f"代码搜索失败: {str(e)}")
    
    def _extract_keywords(self, query: str) -> List[str]:
        """从查询中提取关键词"""
        # 转换为小写
        query_lower = query.lower()
        
        # 移除常见停用词
        stop_words = {
            'how', 'does', 'is', 'are', 'was', 'were', 'the', 'a', 'an',
            'where', 'what', 'when', 'why', 'which', 'who', 'do', 'does',
            'can', 'could', 'should', 'would', 'will', 'to', 'for', 'of',
            'in', 'on', 'at', 'by', 'with', 'from', 'as', 'and', 'or', 'but'
        }
        
        # 提取单词
        words = re.findall(r'\b\w+\b', query_lower)
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        # 也保留原始查询中的重要短语
        important_phrases = []
        phrase_patterns = [
            r'\b\w+\s+\w+\b',  # 两个词的短语
        ]
        for pattern in phrase_patterns:
            phrases = re.findall(pattern, query_lower)
            important_phrases.extend(phrases)
        
        return list(set(keywords + important_phrases))
    
    def _get_search_directories(self, target_dirs: List[str]) -> List[Path]:
        """获取要搜索的目录列表"""
        if target_dirs:
            # 使用指定的目录
            search_dirs = []
            for dir_path in target_dirs:
                full_path = self.work_dir / dir_path if not Path(dir_path).is_absolute() else Path(dir_path)
                if full_path.exists() and full_path.is_dir():
                    search_dirs.append(full_path)
                else:
                    logger.warning(f"目录不存在或不是目录: {dir_path}")
            return search_dirs if search_dirs else [self.work_dir]
        else:
            # 搜索整个工作目录
            return [self.work_dir]
    
    async def _collect_files(
        self,
        search_dirs: List[Path],
        extensions: List[str]
    ) -> List[Path]:
        """收集所有要搜索的文件"""
        files = []
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            
            # 递归遍历目录
            for root, dirs, filenames in os.walk(search_dir):
                # 过滤忽略的目录
                dirs[:] = [d for d in dirs if not self._should_ignore(d)]
                
                for filename in filenames:
                    if self._should_ignore(filename):
                        continue
                    
                    file_path = Path(root) / filename
                    # 检查文件扩展名
                    if extensions and file_path.suffix not in extensions:
                        continue
                    
                    files.append(file_path)
        
        return files
    
    def _should_ignore(self, name: str) -> bool:
        """检查是否应该忽略该文件/目录"""
        for pattern in self.IGNORE_PATTERNS:
            if pattern.startswith('*'):
                # 通配符匹配
                if name.endswith(pattern[1:]):
                    return True
            elif pattern in name:
                return True
        return False
    
    async def _search_files(
        self,
        files: List[Path],
        query: str,
        keywords: List[str],
        min_score: float
    ) -> List[Dict[str, Any]]:
        """并行搜索所有文件"""
        # 限制并发数，避免打开太多文件
        semaphore = asyncio.Semaphore(20)
        
        async def search_file(file_path: Path) -> List[Dict[str, Any]]:
            async with semaphore:
                try:
                    return await self._search_single_file(file_path, query, keywords, min_score)
                except Exception as e:
                    logger.debug(f"搜索文件失败 {file_path}: {str(e)}")
                    return []
        
        # 并行搜索所有文件
        tasks = [search_file(f) for f in files]
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 展平结果
        results = []
        for result_list in results_lists:
            if isinstance(result_list, list):
                results.extend(result_list)
            elif isinstance(result_list, Exception):
                logger.debug(f"搜索任务异常: {str(result_list)}")
        
        return results
    
    async def _search_single_file(
        self,
        file_path: Path,
        query: str,
        keywords: List[str],
        min_score: float
    ) -> List[Dict[str, Any]]:
        """搜索单个文件"""
        try:
            # 读取文件内容
            try:
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
            except UnicodeDecodeError:
                # 尝试其他编码
                try:
                    async with aiofiles.open(file_path, 'r', encoding='gbk') as f:
                        content = await f.read()
                except:
                    return []  # 无法读取的文件，跳过
            except Exception:
                return []  # 其他错误，跳过
            
            if not content:
                return []
            
            # 计算文件级别的相关性
            file_score = self._calculate_relevance(content, query, keywords)
            
            if file_score < min_score:
                return []
            
            # 提取相关代码片段
            snippets = self._extract_code_snippets(content, query, keywords, file_path.suffix)
            
            # 为每个片段计算分数并添加文件信息
            results = []
            for snippet in snippets:
                snippet_score = snippet.get('score', file_score)
                if snippet_score >= min_score:
                    results.append({
                        'file_path': str(file_path.relative_to(self.work_dir)),
                        'absolute_path': str(file_path.absolute()),
                        'code': snippet['code'],
                        'start_line': snippet['start_line'],
                        'end_line': snippet['end_line'],
                        'score': snippet_score,
                        'language': self._detect_language(file_path.suffix)
                    })
            
            return results
            
        except Exception as e:
            logger.debug(f"搜索文件 {file_path} 时出错: {str(e)}")
            return []
    
    def _calculate_relevance(
        self,
        content: str,
        query: str,
        keywords: List[str]
    ) -> float:
        """计算内容与查询的相关性分数（0-1）"""
        content_lower = content.lower()
        query_lower = query.lower()
        
        score = 0.0
        
        # 1. 完整查询匹配（最高权重）
        if query_lower in content_lower:
            score += 0.5
        
        # 2. 关键词匹配
        keyword_matches = sum(1 for keyword in keywords if keyword in content_lower)
        if keywords:
            score += 0.3 * (keyword_matches / len(keywords))
        
        # 3. 函数/类名匹配（如果查询包含函数/类相关的词）
        if any(word in query_lower for word in ['function', 'class', 'method', 'def', 'function']):
            # 查找函数定义
            function_patterns = [
                r'def\s+(\w+)',  # Python
                r'function\s+(\w+)',  # JavaScript
                r'class\s+(\w+)',  # 类定义
                r'const\s+(\w+)\s*=',  # JavaScript const
                r'let\s+(\w+)\s*=',  # JavaScript let
            ]
            for pattern in function_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    score += 0.1
        
        # 4. 注释匹配（注释通常描述功能）
        comment_patterns = [
            r'#\s*(.+)',  # Python 单行注释
            r'//\s*(.+)',  # JavaScript 单行注释
            r'/\*\s*(.+?)\s*\*/',  # 多行注释
        ]
        comment_matches = 0
        for pattern in comment_patterns:
            comments = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            for comment in comments:
                if any(keyword in comment.lower() for keyword in keywords):
                    comment_matches += 1
        
        if comment_matches > 0:
            score += 0.1 * min(comment_matches / 5, 1.0)
        
        # 归一化到 0-1
        return min(score, 1.0)
    
    def _extract_code_snippets(
        self,
        content: str,
        query: str,
        keywords: List[str],
        file_extension: str
    ) -> List[Dict[str, Any]]:
        """提取相关代码片段"""
        lines = content.splitlines()
        snippets = []
        
        # 查找包含关键词的行
        relevant_lines = []
        for i, line in enumerate(lines, 1):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in keywords) or query.lower() in line_lower:
                relevant_lines.append(i)
        
        if not relevant_lines:
            # 如果没有找到相关行，返回文件开头的一部分
            return [{
                'code': '\n'.join(lines[:20]),
                'start_line': 1,
                'end_line': min(20, len(lines)),
                'score': 0.3
            }]
        
        # 为每个相关行提取上下文（前后各5行）
        processed_ranges = set()
        for line_num in relevant_lines:
            start = max(1, line_num - 5)
            end = min(len(lines), line_num + 5)
            
            # 避免重复提取
            range_key = (start, end)
            if range_key in processed_ranges:
                continue
            processed_ranges.add(range_key)
            
            snippet_lines = lines[start-1:end]
            snippet_code = '\n'.join(snippet_lines)
            
            # 计算片段的相关性
            snippet_score = self._calculate_relevance(snippet_code, query, keywords)
            
            snippets.append({
                'code': snippet_code,
                'start_line': start,
                'end_line': end,
                'score': snippet_score
            })
        
        return snippets
    
    def _detect_language(self, extension: str) -> str:
        """根据文件扩展名检测编程语言"""
        language_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.jsx': 'javascript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.h': 'c',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.sh': 'bash',
            '.vue': 'vue',
            '.html': 'html',
            '.css': 'css',
            '.scss': 'scss',
            '.less': 'less',
            '.sql': 'sql',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.json': 'json',
            '.md': 'markdown',
        }
        return language_map.get(extension.lower(), 'text')
    
    def _format_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """格式化搜索结果"""
        formatted = []
        for result in results:
            formatted.append({
                'file_path': result['file_path'],
                'absolute_path': result['absolute_path'],
                'code_snippet': result['code'],
                'start_line': result['start_line'],
                'end_line': result['end_line'],
                'score': round(result['score'], 3),
                'language': result['language']
            })
        return formatted
    
    def _generate_user_summary(
        self,
        results: List[Dict[str, Any]],
        query: str
    ) -> str:
        """生成用户友好的结果摘要"""
        if not results:
            return f"未找到与 '{query}' 相关的代码"
        
        summary_lines = [f"找到 {len(results)} 个相关代码片段：\n"]
        
        for i, result in enumerate(results[:5], 1):  # 只显示前5个
            file_path = result['file_path']
            start_line = result['start_line']
            end_line = result['end_line']
            score = result['score']
            
            summary_lines.append(
                f"{i}. {file_path} (行 {start_line}-{end_line}, 相关性: {score:.2f})"
            )
        
        if len(results) > 5:
            summary_lines.append(f"\n... 还有 {len(results) - 5} 个结果")
        
        return '\n'.join(summary_lines)

