"""
MCPClient使用示例
"""
import asyncio
import os
import sys

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

import asyncio
import json
from backend.mcp_client.client import MCPClient

# 示例配置
config = {
    "mcp_server": {
        "ssemcp": {
            "type": "sse",
            "url": "http://localhost:8000/sse"
        },
        "httpmcp": {
            "type": "streamable_http", 
            "url": "http://localhost:9527/mcp"
        }
    }
}

async def main():
    # 创建MCP客户端
    mcp_client = MCPClient(config)
    
    try:
        # 加载所有MCP服务器
        sessions = await mcp_client.load_mcp_servers()
        print(f"成功加载 {len(sessions)} 个MCP服务器")
        
        # 获取服务器列表
        server_list = mcp_client.get_server_list()
        print(f"已加载的服务器: {server_list}")
        
        # 获取所有服务器的工具
        all_tools = await mcp_client.get_all_tools()
        print(f"所有服务器的工具:")
        for server_name, tools in all_tools.items():
            print(f"  服务器 {server_name}: {len(tools)} 个工具")
            for tool in tools:
                print(f"    - {tool['name']}: {tool['description']}")
        
        # 获取特定服务器的工具
        if "httpmcp" in server_list:
            tools = await mcp_client.get_tools_by_server("httpmcp")
            print(f"httpmcp服务器的工具: {len(tools)} 个")
            
            # 如果有工具，尝试调用第一个工具（示例）
            if tools:
                tool_name = "search_resources"
                try:
                    # 根据工具的input_schema构造参数
                    arguments = {"resources": [{"query": "函数极限"}]}  # 这里需要根据实际工具的schema填写参数
                    result = await mcp_client.call_tool("httpmcp", tool_name, arguments)
                    print(f"调用工具 {tool_name} 结果: {result}")
                except Exception as e:
                    print(f"调用工具失败: {e}")
        
    except Exception as e:
        print(f"错误: {e}")
    finally:
        # 关闭所有会话
        await mcp_client.close_all_sessions()
        print("所有会话已关闭")

if __name__ == "__main__":
    asyncio.run(main())