/**
 * Agent流式执行客户端库
 * 用于连接和处理Agent流式API的JavaScript客户端
 */

class AgentStreamClient {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '';
        this.onEvent = options.onEvent || (() => {});
        this.onError = options.onError || console.error;
        this.onConnect = options.onConnect || (() => {});
        this.onDisconnect = options.onDisconnect || (() => {});
        
        this.isConnected = false;
        this.currentSession = null;
        this.abortController = null;
    }
    
    /**
     * 执行Agent任务
     * @param {Object} request - 执行请求
     * @param {string} request.query - 查询内容
     * @param {string} request.agent_type - Agent类型，默认'PlanAgent'
     * @param {number} request.max_rounds - 最大执行轮数，默认80
     * @param {boolean} request.stream_file_operations - 是否启用流式文件操作，默认true
     * @param {Object} request.llm_config - LLM配置，可选
     */
    async execute(request) {
        if (this.isConnected) {
            this.disconnect();
        }
        
        try {
            this.abortController = new AbortController();
            
            const requestData = {
                query: request.query,
                agent_type: request.agent_type || 'PlanAgent',
                max_rounds: request.max_rounds || 80,
                stream_file_operations: request.stream_file_operations !== false,
                ...request.llm_config && { llm_config: request.llm_config }
            };
            
            const response = await fetch(`${this.baseUrl}/api/v1/agent/execute/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData),
                signal: this.abortController.signal
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            this.isConnected = true;
            this.onConnect();
            
            await this._processStream(response);
            
        } catch (error) {
            if (error.name !== 'AbortError') {
                this.onError(error);
            }
        } finally {
            this.disconnect();
        }
    }
    
    /**
     * 处理流式响应
     */
    async _processStream(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        try {
            while (this.isConnected) {
                const { done, value } = await reader.read();
                
                if (done) break;
                
                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const eventData = JSON.parse(line.slice(6));
                            this._handleEvent(eventData);
                        } catch (e) {
                            console.warn('解析事件数据失败:', e, line);
                        }
                    }
                }
            }
        } finally {
            reader.releaseLock();
        }
    }
    
    /**
     * 处理流式事件
     */
    _handleEvent(event) {
        // 触发通用事件回调
        this.onEvent(event);
        
        // 触发特定事件类型的回调
        const eventHandler = `on${this._toCamelCase(event.event_type)}`;
        if (typeof this[eventHandler] === 'function') {
            this[eventHandler](event);
        }
    }
    
    /**
     * 断开连接
     */
    disconnect() {
        this.isConnected = false;
        
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
        
        this.onDisconnect();
    }
    
    /**
     * 获取活跃会话列表
     */
    async getActiveSessions() {
        try {
            const response = await fetch(`${this.baseUrl}/api/v1/agent/sessions`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            this.onError(error);
            return null;
        }
    }
    
    /**
     * 健康检查
     */
    async healthCheck() {
        try {
            const response = await fetch(`${this.baseUrl}/api/v1/health`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            this.onError(error);
            return null;
        }
    }
    
    /**
     * 工具方法：转换为驼峰命名
     */
    _toCamelCase(str) {
        return str.replace(/_([a-z])/g, (match, letter) => letter.toUpperCase())
                 .replace(/^[a-z]/, match => match.toUpperCase());
    }
}

/**
 * 事件类型常量
 */
AgentStreamClient.EventTypes = {
    AGENT_START: 'agent_start',
    AGENT_CONTENT: 'agent_content',
    TOOL_CALL_START: 'tool_call_start',
    TOOL_ARGS: 'tool_args',
    TOOL_RESULT_START: 'tool_result_start',
    TOOL_RESULT_CONTENT: 'tool_result_content',
    TOOL_RESULT_END: 'tool_result_end',
    FILE_OPERATION: 'file_operation',
    AGENT_ROUND: 'agent_round',
    AGENT_FINISHED: 'agent_finished',
    ERROR: 'error',
    HEARTBEAT: 'heartbeat'
};

/**
 * 便捷的事件处理器基类
 * 可以继承此类并重写相应的事件处理方法
 */
class AgentEventHandler {
    onAgentStart(event) {
        console.log(`🚀 Agent开始执行: ${event.agent_name}`);
    }
    
    onAgentContent(event) {
        console.log(`💬 Agent内容: ${event.content}`);
    }
    
    onToolCallStart(event) {
        console.log(`🔧 工具调用开始: ${event.tool_name}`);
    }
    
    onToolArgs(event) {
        console.log(`📋 工具参数:`, event.tool_args);
        
        if (event.is_streaming_file) {
            console.log(`📁 文件操作: ${event.operation_mode} -> ${event.file_path}`);
        }
    }
    
    onToolResultStart(event) {
        console.log(`📤 工具结果开始: ${event.tool_name}`);
    }
    
    onToolResultContent(event) {
        if (event.is_streaming_file) {
            console.log(`📝 文件内容: ${event.content}`);
        } else {
            console.log(`📋 工具结果: ${event.content}`);
        }
    }
    
    onToolResultEnd(event) {
        console.log(`✅ 工具执行完成: ${event.tool_name}`);
    }
    
    onAgentRound(event) {
        console.log(`🔄 执行轮次: ${event.current_round}`);
        
        if (event.token_usage) {
            console.log(`📊 Token使用: ${event.token_usage.token_count}/${event.token_usage.max_tokens}`);
        }
    }
    
    onAgentFinished(event) {
        console.log(`🎉 Agent执行完成!`);
        console.log(`📊 执行统计:`, event.data);
    }
    
    onError(event) {
        console.error(`❌ 错误: ${event.error_message || event.content}`);
    }
}

/**
 * 使用示例和工厂函数
 */
const AgentStreamClientFactory = {
    /**
     * 创建基础客户端
     */
    createBasicClient(baseUrl = '') {
        return new AgentStreamClient({
            baseUrl,
            onEvent: (event) => console.log('事件:', event.event_type, event),
            onError: (error) => console.error('错误:', error),
            onConnect: () => console.log('✅ 已连接'),
            onDisconnect: () => console.log('❌ 已断开')
        });
    },
    
    /**
     * 创建带事件处理器的客户端
     */
    createClientWithHandler(handler, baseUrl = '') {
        const client = new AgentStreamClient({ baseUrl });
        
        // 绑定事件处理器的方法到客户端
        Object.getOwnPropertyNames(Object.getPrototypeOf(handler))
            .filter(name => name.startsWith('on') && typeof handler[name] === 'function')
            .forEach(methodName => {
                client[methodName] = handler[methodName].bind(handler);
            });
        
        return client;
    },
    
    /**
     * 创建用于React的客户端
     */
    createReactClient(callbacks = {}) {
        return new AgentStreamClient({
            baseUrl: callbacks.baseUrl || '',
            onEvent: callbacks.onEvent || (() => {}),
            onError: callbacks.onError || console.error,
            onConnect: callbacks.onConnect || (() => {}),
            onDisconnect: callbacks.onDisconnect || (() => {})
        });
    }
};

// 导出
if (typeof module !== 'undefined' && module.exports) {
    // Node.js环境
    module.exports = {
        AgentStreamClient,
        AgentEventHandler,
        AgentStreamClientFactory
    };
} else {
    // 浏览器环境
    window.AgentStreamClient = AgentStreamClient;
    window.AgentEventHandler = AgentEventHandler;
    window.AgentStreamClientFactory = AgentStreamClientFactory;
}

/**
 * 使用示例:
 * 
 * // 1. 基础使用
 * const client = new AgentStreamClient({
 *     baseUrl: 'http://localhost:8000',
 *     onEvent: (event) => {
 *         console.log('收到事件:', event.event_type, event.content);
 *     }
 * });
 * 
 * await client.execute({
 *     query: '制定一个计划，计算1+1的结果',
 *     agent_type: 'PlanAgent',
 *     max_rounds: 50
 * });
 * 
 * // 2. 使用事件处理器
 * class MyEventHandler extends AgentEventHandler {
 *     onAgentContent(event) {
 *         document.getElementById('output').textContent += event.content;
 *     }
 *     
 *     onToolResultContent(event) {
 *         if (event.is_streaming_file) {
 *             document.getElementById('fileContent').textContent += event.content;
 *         }
 *     }
 * }
 * 
 * const handler = new MyEventHandler();
 * const client = AgentStreamClientFactory.createClientWithHandler(handler);
 * 
 * // 3. React Hook示例
 * function useAgentStream() {
 *     const [isConnected, setIsConnected] = useState(false);
 *     const [events, setEvents] = useState([]);
 *     
 *     const client = useMemo(() => AgentStreamClientFactory.createReactClient({
 *         onEvent: (event) => setEvents(prev => [...prev, event]),
 *         onConnect: () => setIsConnected(true),
 *         onDisconnect: () => setIsConnected(false)
 *     }), []);
 *     
 *     return { client, isConnected, events };
 * }
 */
