import React, { useState, useEffect, useRef, useCallback } from 'react';
import { AgentStreamClient, AgentEventHandler } from './agent_stream_client.js';

/**
 * Agent流式执行React组件
 * 提供完整的Agent执行界面和实时监控功能
 */
const AgentStreamComponent = ({ 
    baseUrl = '', 
    defaultQuery = '',
    onExecutionComplete,
    className = ''
}) => {
    // 状态管理
    const [isConnected, setIsConnected] = useState(false);
    const [isExecuting, setIsExecuting] = useState(false);
    const [events, setEvents] = useState([]);
    const [agentInfo, setAgentInfo] = useState({
        currentRound: 0,
        executionTime: 0,
        currentTool: null,
        fileOperation: null
    });
    const [tokenUsage, setTokenUsage] = useState(null);
    
    // 表单状态
    const [query, setQuery] = useState(defaultQuery);
    const [agentType, setAgentType] = useState('PlanAgent');
    const [maxRounds, setMaxRounds] = useState(80);
    
    // 引用
    const clientRef = useRef(null);
    const startTimeRef = useRef(null);
    const timerRef = useRef(null);
    const outputRef = useRef(null);
    
    // 自定义事件处理器
    class ReactEventHandler extends AgentEventHandler {
        onAgentStart(event) {
            setEvents(prev => [...prev, { ...event, timestamp: Date.now() }]);
            setAgentInfo(prev => ({ ...prev, currentRound: 0 }));
            startTimeRef.current = Date.now();
        }
        
        onAgentContent(event) {
            setEvents(prev => [...prev, { ...event, timestamp: Date.now() }]);
        }
        
        onToolCallStart(event) {
            setEvents(prev => [...prev, { ...event, timestamp: Date.now() }]);
            setAgentInfo(prev => ({ ...prev, currentTool: event.tool_name }));
        }
        
        onToolArgs(event) {
            setEvents(prev => [...prev, { ...event, timestamp: Date.now() }]);
            
            if (event.is_streaming_file) {
                setAgentInfo(prev => ({
                    ...prev,
                    fileOperation: {
                        path: event.file_path,
                        mode: event.operation_mode
                    }
                }));
            }
        }
        
        onToolResultContent(event) {
            setEvents(prev => [...prev, { ...event, timestamp: Date.now() }]);
        }
        
        onToolResultEnd(event) {
            setEvents(prev => [...prev, { ...event, timestamp: Date.now() }]);
            setAgentInfo(prev => ({ 
                ...prev, 
                currentTool: null,
                fileOperation: null 
            }));
        }
        
        onAgentRound(event) {
            setAgentInfo(prev => ({ ...prev, currentRound: event.current_round }));
            
            if (event.token_usage) {
                setTokenUsage(event.token_usage);
            }
        }
        
        onAgentFinished(event) {
            setEvents(prev => [...prev, { ...event, timestamp: Date.now() }]);
            setIsExecuting(false);
            
            if (onExecutionComplete) {
                onExecutionComplete(event.data);
            }
        }
        
        onError(event) {
            setEvents(prev => [...prev, { ...event, timestamp: Date.now() }]);
            setIsExecuting(false);
        }
    }
    
    // 初始化客户端
    useEffect(() => {
        const handler = new ReactEventHandler();
        
        clientRef.current = new AgentStreamClient({
            baseUrl,
            onEvent: (event) => {
                // 通用事件处理
                const handlerMethod = `on${event.event_type.split('_').map(word => 
                    word.charAt(0).toUpperCase() + word.slice(1)
                ).join('')}`;
                
                if (typeof handler[handlerMethod] === 'function') {
                    handler[handlerMethod](event);
                }
            },
            onConnect: () => setIsConnected(true),
            onDisconnect: () => {
                setIsConnected(false);
                setIsExecuting(false);
            },
            onError: (error) => {
                console.error('Stream error:', error);
                setEvents(prev => [...prev, {
                    event_type: 'error',
                    content: error.message,
                    timestamp: Date.now()
                }]);
                setIsExecuting(false);
            }
        });
        
        return () => {
            if (clientRef.current) {
                clientRef.current.disconnect();
            }
        };
    }, [baseUrl]);
    
    // 执行时间计时器
    useEffect(() => {
        if (isExecuting && startTimeRef.current) {
            timerRef.current = setInterval(() => {
                const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
                setAgentInfo(prev => ({ ...prev, executionTime: elapsed }));
            }, 1000);
        } else {
            if (timerRef.current) {
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
        }
        
        return () => {
            if (timerRef.current) {
                clearInterval(timerRef.current);
            }
        };
    }, [isExecuting]);
    
    // 自动滚动到底部
    useEffect(() => {
        if (outputRef.current) {
            outputRef.current.scrollTop = outputRef.current.scrollHeight;
        }
    }, [events]);
    
    // 执行Agent
    const executeAgent = useCallback(async () => {
        if (!query.trim()) {
            alert('请输入查询内容');
            return;
        }
        
        setIsExecuting(true);
        setEvents([]);
        setTokenUsage(null);
        
        try {
            await clientRef.current.execute({
                query,
                agent_type: agentType,
                max_rounds: maxRounds,
                stream_file_operations: true
            });
        } catch (error) {
            console.error('Execution failed:', error);
        }
    }, [query, agentType, maxRounds]);
    
    // 停止执行
    const stopExecution = useCallback(() => {
        if (clientRef.current) {
            clientRef.current.disconnect();
        }
        setIsExecuting(false);
    }, []);
    
    // 清空输出
    const clearOutput = useCallback(() => {
        setEvents([]);
        setTokenUsage(null);
    }, []);
    
    // 渲染事件项
    const renderEvent = (event, index) => {
        const getEventStyle = (eventType) => {
            const styles = {
                agent_start: { borderLeft: '4px solid #28a745', background: '#f8fff9' },
                agent_content: { borderLeft: '4px solid #007bff', background: '#f8f9ff' },
                tool_call_start: { borderLeft: '4px solid #ffc107', background: '#fffdf8' },
                tool_result_content: { borderLeft: '4px solid #17a2b8', background: '#f8fdff' },
                agent_finished: { borderLeft: '4px solid #28a745', background: '#f8fff9' },
                error: { borderLeft: '4px solid #dc3545', background: '#fff8f8' }
            };
            return styles[eventType] || { borderLeft: '4px solid #6c757d', background: '#f8f9fa' };
        };
        
        return (
            <div
                key={index}
                style={{
                    ...getEventStyle(event.event_type),
                    padding: '8px 12px',
                    marginBottom: '8px',
                    borderRadius: '4px',
                    fontSize: '13px',
                    fontFamily: 'Consolas, Monaco, monospace'
                }}
            >
                <div style={{ 
                    fontSize: '11px', 
                    color: '#666', 
                    marginBottom: '4px',
                    fontWeight: '600'
                }}>
                    [{new Date(event.timestamp).toLocaleTimeString()}] {event.event_type.toUpperCase()}
                    {event.tool_name && (
                        <span style={{
                            background: '#ffc107',
                            color: '#000',
                            padding: '2px 6px',
                            borderRadius: '3px',
                            fontSize: '10px',
                            marginLeft: '8px'
                        }}>
                            {event.tool_name}
                        </span>
                    )}
                    {event.is_streaming_file && (
                        <span style={{
                            background: 'linear-gradient(90deg, #6f42c1, #007bff)',
                            color: 'white',
                            padding: '2px 6px',
                            borderRadius: '3px',
                            fontSize: '10px',
                            marginLeft: '8px'
                        }}>
                            FILE STREAM
                        </span>
                    )}
                </div>
                <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {event.content}
                </div>
            </div>
        );
    };
    
    return (
        <div className={`agent-stream-component ${className}`} style={{ 
            fontFamily: 'system-ui, -apple-system, sans-serif',
            maxWidth: '1200px',
            margin: '0 auto',
            padding: '20px'
        }}>
            {/* 控制面板 */}
            <div style={{
                background: 'white',
                padding: '20px',
                borderRadius: '8px',
                boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
                marginBottom: '20px'
            }}>
                <h2 style={{ marginBottom: '16px', color: '#333' }}>🤖 Agent流式执行</h2>
                
                <div style={{ 
                    display: 'grid', 
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '16px',
                    marginBottom: '16px'
                }}>
                    <div>
                        <label style={{ display: 'block', marginBottom: '4px', fontWeight: '600' }}>
                            查询内容:
                        </label>
                        <textarea
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="请输入要执行的任务..."
                            style={{
                                width: '100%',
                                minHeight: '80px',
                                padding: '8px',
                                border: '1px solid #ddd',
                                borderRadius: '4px',
                                resize: 'vertical'
                            }}
                        />
                    </div>
                    
                    <div>
                        <label style={{ display: 'block', marginBottom: '4px', fontWeight: '600' }}>
                            Agent类型:
                        </label>
                        <select
                            value={agentType}
                            onChange={(e) => setAgentType(e.target.value)}
                            style={{
                                width: '100%',
                                padding: '8px',
                                border: '1px solid #ddd',
                                borderRadius: '4px'
                            }}
                        >
                            <option value="PlanAgent">PlanAgent</option>
                        </select>
                    </div>
                    
                    <div>
                        <label style={{ display: 'block', marginBottom: '4px', fontWeight: '600' }}>
                            最大轮数:
                        </label>
                        <input
                            type="number"
                            value={maxRounds}
                            onChange={(e) => setMaxRounds(parseInt(e.target.value))}
                            min="1"
                            max="200"
                            style={{
                                width: '100%',
                                padding: '8px',
                                border: '1px solid #ddd',
                                borderRadius: '4px'
                            }}
                        />
                    </div>
                </div>
                
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button
                        onClick={executeAgent}
                        disabled={isExecuting}
                        style={{
                            padding: '10px 20px',
                            background: isExecuting ? '#6c757d' : '#007bff',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            cursor: isExecuting ? 'not-allowed' : 'pointer',
                            fontWeight: '600'
                        }}
                    >
                        {isExecuting ? '⏳ 执行中...' : '🚀 开始执行'}
                    </button>
                    
                    <button
                        onClick={stopExecution}
                        disabled={!isExecuting}
                        style={{
                            padding: '10px 20px',
                            background: !isExecuting ? '#6c757d' : '#dc3545',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            cursor: !isExecuting ? 'not-allowed' : 'pointer',
                            fontWeight: '600'
                        }}
                    >
                        ⏹️ 停止
                    </button>
                    
                    <button
                        onClick={clearOutput}
                        style={{
                            padding: '10px 20px',
                            background: '#6c757d',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            cursor: 'pointer',
                            fontWeight: '600'
                        }}
                    >
                        🗑️ 清空
                    </button>
                </div>
            </div>
            
            {/* 状态栏 */}
            <div style={{
                background: 'white',
                padding: '16px',
                borderRadius: '8px',
                boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
                marginBottom: '20px',
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
                gap: '16px',
                textAlign: 'center'
            }}>
                <div>
                    <div style={{ fontSize: '12px', color: '#666', fontWeight: '600' }}>连接状态</div>
                    <div style={{ fontSize: '16px', fontWeight: 'bold', color: isConnected ? '#28a745' : '#dc3545' }}>
                        {isConnected ? '已连接' : '未连接'}
                    </div>
                </div>
                
                <div>
                    <div style={{ fontSize: '12px', color: '#666', fontWeight: '600' }}>当前轮次</div>
                    <div style={{ fontSize: '16px', fontWeight: 'bold' }}>
                        {agentInfo.currentRound}
                    </div>
                </div>
                
                <div>
                    <div style={{ fontSize: '12px', color: '#666', fontWeight: '600' }}>执行时间</div>
                    <div style={{ fontSize: '16px', fontWeight: 'bold' }}>
                        {agentInfo.executionTime}s
                    </div>
                </div>
                
                <div>
                    <div style={{ fontSize: '12px', color: '#666', fontWeight: '600' }}>当前工具</div>
                    <div style={{ fontSize: '16px', fontWeight: 'bold' }}>
                        {agentInfo.currentTool || '无'}
                    </div>
                </div>
                
                <div>
                    <div style={{ fontSize: '12px', color: '#666', fontWeight: '600' }}>文件操作</div>
                    <div style={{ fontSize: '16px', fontWeight: 'bold' }}>
                        {agentInfo.fileOperation ? 
                            `${agentInfo.fileOperation.mode}: ${agentInfo.fileOperation.path}` : 
                            '无'
                        }
                    </div>
                </div>
            </div>
            
            {/* 主要内容区域 */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 300px',
                gap: '20px'
            }}>
                {/* 输出面板 */}
                <div style={{
                    background: 'white',
                    borderRadius: '8px',
                    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
                    overflow: 'hidden'
                }}>
                    <div style={{
                        background: '#f8f9fa',
                        padding: '12px 16px',
                        borderBottom: '1px solid #dee2e6',
                        fontWeight: '600'
                    }}>
                        📝 实时输出 ({events.length} 条事件)
                    </div>
                    
                    <div
                        ref={outputRef}
                        style={{
                            height: '500px',
                            overflowY: 'auto',
                            padding: '16px'
                        }}
                    >
                        {events.length === 0 ? (
                            <div style={{ 
                                textAlign: 'center', 
                                color: '#666', 
                                padding: '40px',
                                fontStyle: 'italic'
                            }}>
                                等待执行...
                            </div>
                        ) : (
                            events.map(renderEvent)
                        )}
                    </div>
                </div>
                
                {/* 侧边栏 */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {/* Token使用情况 */}
                    <div style={{
                        background: 'white',
                        borderRadius: '8px',
                        boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
                        overflow: 'hidden'
                    }}>
                        <div style={{
                            background: '#f8f9fa',
                            padding: '12px 16px',
                            borderBottom: '1px solid #dee2e6',
                            fontWeight: '600'
                        }}>
                            📊 Token使用情况
                        </div>
                        
                        <div style={{ padding: '16px' }}>
                            {tokenUsage ? (
                                <>
                                    <div style={{ marginBottom: '8px' }}>
                                        <strong>当前Token:</strong> {tokenUsage.token_count || 0}
                                    </div>
                                    <div style={{ marginBottom: '8px' }}>
                                        <strong>最大Token:</strong> {tokenUsage.max_tokens || 0}
                                    </div>
                                    <div style={{ marginBottom: '8px' }}>
                                        <strong>使用率:</strong> {((tokenUsage.usage_ratio || 0) * 100).toFixed(1)}%
                                    </div>
                                    <div>
                                        <strong>需要压缩:</strong> {tokenUsage.needs_compression ? '是' : '否'}
                                    </div>
                                </>
                            ) : (
                                <div style={{ color: '#666', fontStyle: 'italic' }}>
                                    等待执行...
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AgentStreamComponent;
