from typing import Dict, Any, Optional
from loguru import logger

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

class MCPClient:
    def __init__(self, config: Dict[str, Any]):
        """
        初始化MCP客户端
        
        example: 
        {
            "mcp_server": {   // mcp_server 固定名称
                "testmcp": {
                    "type": "sse",
                    "url": "http://localhost:8000/sse"
                },
                "httpmcp": {
                    "type": "streamable_http",
                    "url": "http://localhost:8001/mcp"
                }
            }
        }
        Args:
            config: MCP服务器配置字典
        """
        self.config = config
        self.sessions: Dict[str, ClientSession] = {}
        self.clients: Dict[str, Any] = {}
        
    async def load_mcp_servers(self) -> Dict[str, ClientSession]:
        """
        加载所有配置的MCP服务器
        
        Returns:
            Dict[str, ClientSession]: 服务器名称到会话的映射
        """
        if "mcp_server" not in self.config:
            logger.warning("配置中未找到mcp_server部分")
            return self.sessions
            
        mcp_servers = self.config["mcp_server"]
        
        for server_name, server_config in mcp_servers.items():
            try:
                await self._load_single_server(server_name, server_config)
                logger.info(f"成功加载MCP服务器: {server_name}")
            except Exception as e:
                logger.error(f"加载MCP服务器 {server_name} 失败: {str(e)}")
                
        return self.sessions
    
    async def _load_single_server(self, server_name: str, server_config: Dict[str, Any]):
        """
        加载单个MCP服务器
        
        Args:
            server_name: 服务器名称
            server_config: 服务器配置
        """
        server_type = server_config.get("type")
        server_url = server_config.get("url")
        
        if not server_type or not server_url:
            raise ValueError(f"服务器 {server_name} 配置缺少type或url")
            
        if server_type == "sse":
            await self._load_sse_server(server_name, server_url)
        elif server_type == "streamable_http":
            await self._load_streamable_http_server(server_name, server_url)
        else:
            raise ValueError(f"不支持的服务器类型: {server_type}")
    
    async def _load_sse_server(self, server_name: str, server_url: str):
        """
        加载SSE类型的MCP服务器
        
        Args:
            server_name: 服务器名称
            server_url: 服务器URL
        """
        try:
            # 创建SSE客户端上下文管理器
            client_context = sse_client(server_url)
            # 进入上下文管理器获取streams
            read_stream, write_stream = await client_context.__aenter__()
            self.clients[server_name] = client_context
            
            # 创建客户端会话 - streams可能是单个对象包含read/write
            session_context = ClientSession(read_stream, write_stream)
            
            # 初始化会话
            session = await session_context.__aenter__()
            await session.initialize()
            
            self.sessions[server_name] = session
            
            logger.info(f"SSE服务器 {server_name} 连接成功")
            
        except Exception as e:
            logger.error(f"连接SSE服务器 {server_name} 失败: {str(e)}")
            raise
    
    async def _load_streamable_http_server(self, server_name: str, server_url: str):
        """
        加载Streamable HTTP类型的MCP服务器
        
        Args:
            server_name: 服务器名称
            server_url: 服务器URL
        """
        try:
            # 创建Streamable HTTP客户端上下文管理器
            client_context = streamablehttp_client(server_url)
            # 进入上下文管理器获取streams
            read_stream, write_stream, _ = await client_context.__aenter__()
            self.clients[server_name] = client_context
            
            # 创建客户端会话 - streams可能是单个对象包含read/write
            session_context = ClientSession(read_stream, write_stream)
            
            # 初始化会话
            session = await session_context.__aenter__()
            await session.initialize()
            
            self.sessions[server_name] = session
            
            logger.info(f"Streamable HTTP服务器 {server_name} 连接成功")
            
        except Exception as e:
            logger.error(f"连接Streamable HTTP服务器 {server_name} 失败: {str(e)}")
            raise
    
    async def get_session(self, server_name: str) -> Optional[ClientSession]:
        """
        获取指定服务器的会话
        
        Args:
            server_name: 服务器名称
            
        Returns:
            ClientSession: 客户端会话，如果不存在则返回None
        """
        return self.sessions.get(server_name)
    
    async def close_all_sessions(self):
        """
        关闭所有会话
        """
        for server_name, session in self.sessions.items():
            try:
                await session.__aexit__(None, None, None)
                logger.info(f"会话 {server_name} 已关闭")
            except Exception as e:
                logger.error(f"关闭会话 {server_name} 失败: {str(e)}")
        
        # 关闭客户端连接
        for server_name, client_context in self.clients.items():
            try:
                await client_context.__aexit__(None, None, None)
                logger.info(f"客户端连接 {server_name} 已关闭")
            except Exception as e:
                logger.error(f"关闭客户端连接 {server_name} 失败: {str(e)}")
        
        self.sessions.clear()
        self.clients.clear()
    
    def get_server_list(self) -> list[str]:
        """
        获取已加载的服务器列表
        
        Returns:
            list[str]: 服务器名称列表
        """
        return list(self.sessions.keys())
    
    async def get_all_tools(self) -> Dict[str, list]:
        """
        获取所有session中的工具
        
        Returns:
            Dict[str, list]: 服务器名称到工具列表的映射
        """
        all_tools = {}
        
        for server_name, session in self.sessions.items():
            try:
                # 列出服务器的工具
                tools_result = await session.list_tools()
                tools = tools_result.tools if hasattr(tools_result, 'tools') else []
                
                # 转换为字典格式便于使用
                tool_list = []
                for tool in tools:
                    tool_info = {
                        'name': tool.name,
                        'description': tool.description if hasattr(tool, 'description') else '',
                        'input_schema': tool.inputSchema if hasattr(tool, 'inputSchema') else {}
                    }
                    tool_list.append(tool_info)
                
                all_tools[server_name] = tool_list
                logger.info(f"从服务器 {server_name} 获取到 {len(tool_list)} 个工具")
                
            except Exception as e:
                logger.error(f"获取服务器 {server_name} 工具失败: {str(e)}")
                all_tools[server_name] = []
        
        return all_tools
    
    async def get_tools_by_server(self, server_name: str) -> list:
        """
        获取指定服务器的工具
        
        Args:
            server_name: 服务器名称
            
        Returns:
            list: 工具列表
        """
        if server_name not in self.sessions:
            logger.warning(f"服务器 {server_name} 不存在")
            return []
            
        try:
            session = self.sessions[server_name]
            tools_result = await session.list_tools()
            tools = tools_result.tools if hasattr(tools_result, 'tools') else []
            
            tool_list = []
            for tool in tools:
                tool_info = {
                    'name': tool.name,
                    'description': tool.description if hasattr(tool, 'description') else '',
                    'input_schema': tool.inputSchema if hasattr(tool, 'inputSchema') else {}
                }
                tool_list.append(tool_info)
            
            logger.info(f"从服务器 {server_name} 获取到 {len(tool_list)} 个工具")
            return tool_list
            
        except Exception as e:
            logger.error(f"获取服务器 {server_name} 工具失败: {str(e)}")
            return []
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        调用指定服务器的工具
        
        Args:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            Any: 工具执行结果
        """
        if server_name not in self.sessions:
            raise ValueError(f"服务器 {server_name} 不存在")
            
        try:
            session = self.sessions[server_name]
            result = await session.call_tool(tool_name, arguments)
            logger.info(f"成功调用服务器 {server_name} 的工具 {tool_name}")
            return result
            
        except Exception as e:
            logger.error(f"调用服务器 {server_name} 的工具 {tool_name} 失败: {str(e)}")
            raise