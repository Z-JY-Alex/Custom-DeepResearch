import os
import httpx
import asyncio
from typing import Any, Dict
from backend.tools.base import BaseTool, ToolCallResult, ToolError
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
        },
        "required": ["query"],
    }
   

    async def execute(self, **kwargs):
        
        client = AsyncTavilyClient("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")
        input_param = {**kwargs, "include_answer":"advanced"}
        try:
            response = await client.search(**input_param)
            return response
        except Exception as e:
            return f"Tavily Search API 调用失败: {str(e)}"

        
        