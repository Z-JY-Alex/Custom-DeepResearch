import os
import httpx
import asyncio
import traceback
from typing import Any, Dict
from backend.tools.base import BaseTool, ToolCallResult
from tavily import AsyncTavilyClient



COUNTRIES = [
    "afghanistan", "albania", "algeria", "andorra", "angola", "argentina", "armenia", 
    "australia", "austria", "azerbaijan", "bahamas", "bahrain", "bangladesh", "barbados", 
    "belarus", "belgium", "belize", "benin", "bhutan", "bolivia", "bosnia and herzegovina", 
    "botswana", "brazil", "brunei", "bulgaria", "burkina faso", "burundi", "cambodia", 
    "cameroon", "canada", "cape verde", "central african republic", "chad", "chile", 
    "china", "colombia", "comoros", "congo", "costa rica", "croatia", "cuba", "cyprus", 
    "czech republic", "denmark", "djibouti", "dominican republic", "ecuador", "egypt", 
    "el salvador", "equatorial guinea", "eritrea", "estonia", "ethiopia", "fiji", 
    "finland", "france", "gabon", "gambia", "georgia", "germany", "ghana", "greece", 
    "guatemala", "guinea", "haiti", "honduras", "hungary", "iceland", "india", "indonesia", 
    "iran", "iraq", "ireland", "israel", "italy", "jamaica", "japan", "jordan", "kazakhstan", 
    "kenya", "kuwait", "kyrgyzstan", "latvia", "lebanon", "lesotho", "liberia", "libya", 
    "liechtenstein", "lithuania", "luxembourg", "madagascar", "malawi", "malaysia", 
    "maldives", "mali", "malta", "mauritania", "mauritius", "mexico", "moldova", "monaco", 
    "mongolia", "montenegro", "morocco", "mozambique", "myanmar", "namibia", "nepal", 
    "netherlands", "new zealand", "nicaragua", "niger", "nigeria", "north korea", 
    "north macedonia", "norway", "oman", "pakistan", "panama", "papua new guinea", 
    "paraguay", "peru", "philippines", "poland", "portugal", "qatar", "romania", "russia", 
    "rwanda", "saudi arabia", "senegal", "serbia", "singapore", "slovakia", "slovenia", 
    "somalia", "south africa", "south korea", "south sudan", "spain", "sri lanka", "sudan", 
    "sweden", "switzerland", "syria", "taiwan", "tajikistan", "tanzania", "thailand", 
    "togo", "trinidad and tobago", "tunisia", "turkey", "turkmenistan", "uganda", "ukraine", 
    "united arab emirates", "united kingdom", "united states", "uruguay", "uzbekistan", 
    "venezuela", "vietnam", "yemen", "zambia", "zimbabwe"
]


class TavilySearch(BaseTool):
    """Tavily Search API"""
    name: str = "tavily_search"
    description: str = """调用 Tavily 搜索接口查询网络信息。每次 query 必须是一个完整的问题或一个独立的关键词，不能在一个 query 中并列多个关键词或问题。例如：query="泛突厥主义历史起源 发展演变 代表人物" 是错误的；正确做法是分别使用：泛突厥主义历史起源、泛突厥主义发展演变、泛突厥主义代表人物。"""
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要执行的搜索查询，例如：'梅西是谁？'",
            },
            "auto_parameters": {
                "type": "boolean",
                "description": "是否自动根据查询内容和意图配置搜索参数。",
                "default": False,
            },
            "topic": {
                "type": "string",
                "description": "搜索类别：general（通用）、news（新闻）、finance（财经）。",
                "enum": ["general", "news", "finance"],
                "default": "general",
            },
            "search_depth": {
                "type": "string",
                "description": "搜索深度：basic（基础，1积分）或 advanced（高级，2积分）。",
                "enum": ["basic", "advanced"],
                "default": "basic",
            },
            "chunks_per_source": {
                "type": "integer",
                "description": "每个结果来源返回的内容片段数量（1-3），每个片段不超过500字符。",
                "minimum": 3,
                "maximum": 5,
                "default": 3,
            },
            "max_results": {
                "type": "integer",
                "description": "返回的搜索结果数量（0-20）。",
                "minimum": 0,
                "maximum": 20,
                "default": 5,
            },
            "time_range": {
                "type": "string",
                "description": "根据发布时间过滤结果的时间范围，可选值：day（天）、week（周）、month（月）、year（年），或缩写 d/w/m/y。",
                "enum": ["day", "week", "month", "year", "d", "w", "m", "y"],
            },
            "days": {
                "type": "integer",
                "description": "向前追溯的天数，仅当 topic=news 时有效。",
                "minimum": 1,
                "default": 7,
            },
            "start_date": {
                "type": "string",
                "description": "仅返回此日期之后的结果，格式：YYYY-MM-DD。",
            },
            "end_date": {
                "type": "string",
                "description": "仅返回此日期之前的结果，格式：YYYY-MM-DD。",
            },
            "include_domains": {
                "type": "array",
                "description": "需要特别包含的域名列表（最多 300 个）。",
                "items": {"type": "string"},
            },
            "exclude_domains": {
                "type": "array",
                "description": "需要排除的域名列表（最多 150 个）。",
                "items": {"type": "string"},
            },
            "country": {
                "type": "string",
                "description": "优先展示来自某个国家的搜索结果（仅当 topic=general 时有效）。",
                "enum": COUNTRIES,
                "default": "china"
            },
            "include_images": {
                "type": "boolean",
                "description": "是否在搜索结果中包含图片。",
                "default": True,
            },
            "include_image_descriptions": {
                "type": "boolean",
                "description": "是否为图片生成描述信息。",
                "default": True,
            }
        },
        "required": ["query"],
    }
    parallel: bool = True
   

    def _format_results_for_user(self, response: Dict) -> str:
        """将搜索结果格式化为用户友好的 Markdown 格式（仅标题和URL）"""
        if isinstance(response, str):  # 错误信息
            return response

        markdown_content = ""

        # 处理搜索结果 - 仅标题和URL
        results = response.get("results", [])
        if results:
            markdown_content += "## 搜索结果\n\n"
            for i, result in enumerate(results, 1):
                title = result.get("title", "无标题")
                url = result.get("url", "")
                markdown_content += f"{i}. [{title}]({url})\n"

        return markdown_content

    def _format_results_to_markdown(self, response: Dict) -> str:
        """将搜索结果格式化为完整的 Markdown 格式（包含所有详细信息）"""
        if isinstance(response, str):  # 错误信息
            return response

        markdown_content = ""

        # 处理搜索结果 - 完整内容
        results = response.get("results", [])
        if results:
            markdown_content += "## 相关内容\n\n"
            for i, result in enumerate(results, 1):
                title = result.get("title", "无标题")
                url = result.get("url", "")
                content = result.get("content", "")
                score = result.get("score", "")

                markdown_content += f"### {i}. [{title}]({url})\n"
                if score:
                    markdown_content += f"**相关度**: {score}\n"
                if content:
                    markdown_content += f"**内容**: {content}\n"
                markdown_content += "\n"

        # 处理图片结果
        images = response.get("images", [])
        if images:
            markdown_content += "\n## 相关图片\n\n"
            for i, image in enumerate(images, 1):
                image_url = image.get("url", "")
                image_title = image.get("title", f"图片 {i}")
                image_description = image.get("description", "")

                markdown_content += f"### {image_title}\n"
                if image_url:
                    markdown_content += f"**链接**: {image_url}\n"

                if image_description:
                    markdown_content += f"**描述**: {image_description}\n"

                markdown_content += "\n"

        return markdown_content

    async def execute(self, **kwargs):
        """执行 Tavily 搜索"""
        try:
            client = AsyncTavilyClient("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")

            if "include_images" not in kwargs:
                kwargs["include_images"] = True
            if "include_image_descriptions" not in kwargs:
                kwargs["include_image_descriptions"] = True

            # 构建搜索参数
            input_param = {**kwargs, "include_answer": "advanced"}

            # 执行搜索
            response = await client.search(**input_param)

            # 检查响应是否有效
            if not response:
                return ToolCallResult(
                    tool_call_id="",
                    error="搜索未返回任何结果"
                )

            # 生成用户友好的结果（仅标题和URL）
            user_friendly_result = self._format_results_for_user(response)

            # 生成完整的内部结果（包含所有详细信息）
            internal_result = self._format_results_to_markdown(response)

            return ToolCallResult(
                tool_call_id="",
                user_result=user_friendly_result,
                result=internal_result
            )

        except (ValueError, TypeError, KeyError) as e:
            # 参数错误
            tb = traceback.format_exc()
            error_msg = f"Tavily Search 参数错误: {str(e)}\n\nTraceback:\n{tb}"
            return ToolCallResult(
                tool_call_id="",
                error=error_msg
            )
        except (httpx.HTTPError, httpx.RequestError) as e:
            # 网络错误
            tb = traceback.format_exc()
            error_msg = f"Tavily Search 网络错误: {str(e)}\n\nTraceback:\n{tb}"
            return ToolCallResult(
                tool_call_id="",
                error=error_msg
            )
        except BaseException as e:
            # 捕获所有其他异常（包括 Exception 和 系统异常）
            tb = traceback.format_exc()
            error_msg = f"Tavily Search API 调用失败: {type(e).__name__}: {str(e)}\n\nTraceback:\n{tb}"
            return ToolCallResult(
                tool_call_id="",
                error=error_msg
            )

        
        