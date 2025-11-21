/**
 * AI助手前端应用 - 流式对话界面
 * 支持Server-Sent Events流式响应
 */

class AIAssistantApp {
    constructor() {
        this.eventSource = null;
        this.isConnected = false;
        this.messageBuffer = new Map(); // 用于缓存流式消息
        this.currentMessageElement = null;
        this.currentToolCall = null;
        this.lastCompletedToolCall = null; // 最后一个完成的工具调用，用于追加后续的 agent_content
        this.toolCallMap = new Map(); // 使用 call_id 映射工具调用元素，支持并发工具调用
        this.toolCallStates = new Map(); // 跟踪每个工具调用的状态

        // 完全隐藏的工具列表（调用和结果都不显示）
        this.fullyHiddenTools = ['artifact_write', 'terminate', 'sub_agent_run'];

        // 只隐藏调用框的工具列表（结果正常显示）
        this.hideCallOnlyTools = ['ask_user'];

        // 事件队列：确保事件按顺序处理
        this.eventQueue = [];
        this.isProcessingQueue = false;
        this.eventProcessingPromise = Promise.resolve();

        // 并发工具调用计数器
        this.activeConcurrentTools = 0;
        this.maxConcurrentTools = 10; // 最大并发工具数限制

        // 数据缓冲区，用于处理分块传输的JSON数据
        this.dataBuffer = '';

        // 思考内容缓冲区，用于处理流式传输的思考标签和被分割的标签
        this.thinkBuffer = '';
        this.tagBuffer = ''; // 新增：用于缓存可能被分割的标签

        // 当前正在流式显示的思考块
        this.currentThinkBlock = null;
        this.currentThinkElement = null;
        this.isInThinkBlock = false;

        // 滚动控制相关
        this.userScrolledUp = false; // 用户是否手动向上滚动
        this.scrollThreshold = 100; // 距离底部多少像素内认为是在底部
        this.lastScrollTop = 0; // 上次滚动位置
        this.scrollToBottomButton = null; // 滚动到底部按钮

        // 文件内容流式显示相关
        this.currentFilePath = null; // 当前打开的文件路径
        this.currentFileMode = null; // 当前文件的操作模式

        // API配置
        this.apiBaseUrl = 'http://localhost:8000/api/v1';

        // 会话ID：每个对话框维持一个session_id
        this.sessionId = this.generateUUID();
        console.log('初始化会话ID:', this.sessionId);

        // 初始化
        this.initializeElements();
        this.bindEvents();
        this.setupAutoResize();
    }

    /**
     * 初始化DOM元素引用
     */
    initializeElements() {
        this.elements = {
            chatMessages: document.getElementById('chatMessages'),
            messageInput: document.getElementById('messageInput'),
            sendButton: document.getElementById('sendButton'),
            statusText: document.getElementById('statusText'),
            sidebar: document.getElementById('sidebar'),
            sidebarTitle: document.getElementById('sidebarTitle'),
            fileContent: document.getElementById('fileContent')
        };
    }

    /**
     * 绑定事件监听器
     */
    bindEvents() {
        // 发送按钮点击
        this.elements.sendButton.addEventListener('click', () => this.sendMessage());
        
        // 输入框回车发送
        this.elements.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // 聊天区域滚动事件监听
        this.elements.chatMessages.addEventListener('scroll', (e) => {
            this.handleScroll(e);
        });
    }

    /**
     * 设置输入框自动调整高度
     */
    setupAutoResize() {
        const input = this.elements.messageInput;
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 120) + 'px';
        });
    }

    /**
     * 发送消息
     */
    async sendMessage() {
        const message = this.elements.messageInput.value.trim();
        if (!message) return;

        console.log('发送消息:', message, '连接状态:', this.isConnected);

        // 如果AI正在执行中，不允许发送新消息
        if (this.isConnected) {
            console.log('AI正在执行中，无法发送新消息');
            return;
        }

        console.log('开始发送消息流程');

        // 显示用户消息
        this.addUserMessage(message);
        this.elements.messageInput.value = '';
        this.elements.messageInput.style.height = 'auto';

        // 禁用输入
        this.setInputEnabled(false);
        this.updateStatus('正在连接...', 'connecting');

        try {
            await this.startAgentExecution(message);
        } catch (error) {
            console.error('发送消息失败:', error);
            this.addErrorMessage('发送失败，请检查网络连接');
            this.setInputEnabled(true);
            this.updateStatus('连接失败', 'error');
        }
    }


    /**
     * 开始Agent执行
     */
    async startAgentExecution(query) {
        const requestData = {
            query: query,
            agent_type: "PlanAgent",
            max_rounds: 80,
            stream_file_operations: true,
            session_id: this.sessionId  // 使用维持的session_id
        };

        console.log('====== 发送Agent请求 ======');
        console.log('session_id:', this.sessionId);
        console.log('完整请求数据:', JSON.stringify(requestData, null, 2));
        console.log('===========================');

        try {
            const response = await fetch(`${this.apiBaseUrl}/agent/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });

            console.log('请求已发送，等待响应...');
            console.log('响应状态:', response.status, response.statusText);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // 创建EventSource连接
            this.setupEventSource(response);

        } catch (error) {
            console.error('启动Agent执行失败:', error);
            this.addErrorMessage(`启动失败: ${error.message}`);
            this.setInputEnabled(true);
            this.updateStatus('就绪', 'ready');
        }
    }

    /**
     * 设置Server-Sent Events连接
     */
    setupEventSource(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        this.isConnected = true;
        this.updateStatus('AI正在思考...', 'processing');

        // 重置所有缓冲区
        this.dataBuffer = '';
        this.thinkBuffer = '';
        this.tagBuffer = '';
        this.currentThinkBlock = null;
        this.currentThinkElement = null;
        this.isInThinkBlock = false;

        // 添加AI消息容器
        this.currentMessageElement = this.addAssistantMessage('');
        
        const readStream = async () => {
            try {
                while (true) {
                    const { done, value } = await reader.read();
                    
                    if (done) {
                        console.log('流结束');
                        break;
                    }
                    
                    const chunk = decoder.decode(value, { stream: true });
                    
                    // 将新的数据块添加到缓冲区
                    if (!this.dataBuffer) {
                        this.dataBuffer = '';
                    }
                    this.dataBuffer += chunk;
                    
                    // 按行分割，但保留最后一个可能不完整的行
                    const lines = this.dataBuffer.split('\n');
                    this.dataBuffer = lines.pop() || ''; // 保留最后一个可能不完整的行
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const jsonStr = line.slice(6).trim();
                            if (!jsonStr) continue; // 跳过空行
                            
                            try {
                                const eventData = JSON.parse(jsonStr);
                                
                                // 对工具事件进行特别标记
                                if (eventData.event_type && eventData.event_type.startsWith('tool_')) {
                                    console.log('🎯 收到工具事件:', eventData.event_type, 'call_id:', eventData.tool?.call_id);
                                } else {
                                    console.log('📨 收到事件:', eventData.event_type);
                                }
                                
                                // 将事件加入队列，按顺序处理
                                this.enqueueEvent(eventData);
                            } catch (e) {
                                console.error('❌ JSON解析失败:', e.message);
                                console.error('📄 原始数据长度:', jsonStr.length);
                                console.error('📄 数据预览:', jsonStr.substring(0, 200) + '...');
                                console.error('📄 数据结尾:', '...' + jsonStr.substring(Math.max(0, jsonStr.length - 200)));
                                
                                // 尝试修复常见的JSON问题
                                const fixedJson = this.tryFixJson(jsonStr);
                                if (fixedJson) {
                                    try {
                                        const eventData = JSON.parse(fixedJson);
                                        console.log('✅ JSON修复成功，继续处理事件');
                                        this.enqueueEvent(eventData);
                                    } catch (e2) {
                                        console.error('❌ JSON修复后仍然失败:', e2.message);
                                    }
                                }
                            }
                        }
                    }
                }
            } catch (error) {
                console.error('读取流数据失败:', error);
                this.addErrorMessage('连接中断，请重试');
            } finally {
                this.isConnected = false;
                this.setInputEnabled(true);
                this.updateStatus('就绪', 'ready');
            }
        };
        
        readStream();
    }

    /**
     * 将事件加入队列，确保按顺序处理
     */
    enqueueEvent(event) {
        this.eventQueue.push(event);
        // 如果当前没有在处理队列，则开始处理
        if (!this.isProcessingQueue) {
            this.processEventQueue();
        }
    }

    /**
     * 按顺序处理事件队列
     */
    async processEventQueue() {
        // 如果正在处理队列，直接返回（避免并发处理）
        if (this.isProcessingQueue) {
            return;
        }

        this.isProcessingQueue = true;

        // 使用 Promise 链确保事件按顺序处理
        // 每次只处理一个事件，处理完后再处理下一个
        while (this.eventQueue.length > 0) {
            const event = this.eventQueue.shift();
            try {
                // 将事件处理添加到 Promise 链中，确保前一个事件处理完成后再处理下一个
                this.eventProcessingPromise = this.eventProcessingPromise.then(async () => {
                    await this.handleStreamEvent(event);
                });
                // 等待当前事件处理完成
                await this.eventProcessingPromise;
            } catch (error) {
                console.error('处理事件失败:', error, event);
            }
        }

        this.isProcessingQueue = false;
    }

    /**
     * 处理流式事件
     */
    async handleStreamEvent(event) {
        console.log('🎯 处理事件:', event.event_type, 'call_id:', event.tool?.call_id, 'tool_name:', event.tool?.name);
        
        // 对于工具相关事件，输出更详细的信息
        if (event.event_type.startsWith('tool_')) {
            console.log('🔧 工具事件详情:', {
                event_type: event.event_type,
                call_id: event.tool?.call_id,
                tool_name: event.tool?.name || event.tool_name,
                has_content: !!event.content,
                content_length: event.content ? event.content.length : 0,
                content_preview: event.content ? event.content.substring(0, 50) + '...' : 'null'
            });
        }
        
        // 统一事件结构：使用 AgentStreamPayload
        const toolName = event.tool?.name;
        switch (event.event_type) {
            case 'agent_start':
                this.handleAgentStart(event);
                break;
                
            case 'agent_content':
                this.handleAgentContent(event);
                break;
                
            case 'tool_call_start':
                this.handleToolCallStart({ ...event, tool_name: toolName });
                break;
                
            case 'tool_args':
                this.handleToolArgs({ ...event, tool_name: toolName });
                break;
                
            case 'tool_result_start':
                this.handleToolResultStart({ ...event, tool_name: toolName });
                break;
                
            case 'tool_result_content':
                this.handleToolResultContent({ ...event, tool_name: toolName });
                break;
                
            case 'tool_result_end':
                this.handleToolResultEnd({ ...event, tool_name: toolName });
                break;
                
            case 'agent_running':
                this.handleAgentRunning(event);
                break;
                
            case 'agent_finished':
                this.handleAgentFinished(event);
                break;
                
            case 'ask_user':
                this.handleAskUser(event);
                break;
                
            case 'error':
                this.handleError(event);
                break;
                
            default:
                console.log('未处理的事件类型:', event.event_type);
        }
    }

    /**
     * 处理Agent开始事件
     */
    handleAgentStart(event) {
        // 不需要更新sessionId，因为前端已经维持了自己的sessionId
        // 如果后端返回了session_id，可以用来验证
        if (event.session_id && event.session_id !== this.sessionId) {
            console.warn('后端返回的session_id与前端不一致:', {
                frontend: this.sessionId,
                backend: event.session_id
            });
        }
        this.updateStatus(`${event.agent_name || 'Agent'} 开始执行`, 'processing');
    }

    /**
     * 处理Agent内容事件 - 立即流式显示
     */
    handleAgentContent(event) {
        if (event.content && this.currentMessageElement) {
            console.log('收到Agent内容:', JSON.stringify(event.content));

            // 立即处理内容，不再使用缓存队列
            // 根据当前状态决定输出位置
            if (this.currentToolCall) {
                // 如果有正在执行的工具，追加到工具内容区域
                this.appendToToolContent(event.content);
            } else if (this.lastCompletedToolCall) {
                // 如果有刚完成的工具，追加到工具后的内容区域
                this.appendToToolAfterContent(event.content);
            } else {
                // 否则追加到消息区域
                this.appendToCurrentMessage(event.content);
            }
        }
    }

    /**
     * 处理工具调用开始事件
     */
    handleToolCallStart(event) {
        const callId = event.tool?.call_id;
        const toolName = event.tool_name || event.tool?.name || '未知工具';

        console.log(`🚀 工具调用开始: ${toolName} (call_id: ${callId})`);

        // 检查是否需要隐藏工具调用框
        const shouldHideCall = this.fullyHiddenTools.includes(toolName) || this.hideCallOnlyTools.includes(toolName);

        if (shouldHideCall) {
            console.log(`🔇 ${toolName} 工具不显示调用框`);

            // 对于只隐藏调用框的工具（如 ask_user），完全不创建工具元素
            // 这样结果会直接显示为普通文本
            if (this.hideCallOnlyTools.includes(toolName)) {
                console.log(`✅ ${toolName} 工具完全跳过DOM创建，结果将作为普通文本显示`);
                // 不创建任何元素，直接返回
                return;
            }

            // 对于完全隐藏的工具（如 artifact_write、terminate），创建隐藏元素用于状态跟踪
            const toolCallElement = this.createToolCallElement(toolName, callId);
            toolCallElement.style.display = 'none';

            // 存储映射和状态
            if (callId) {
                this.toolCallMap.set(callId, toolCallElement);
                this.toolCallStates.set(callId, {
                    status: 'starting',
                    toolName: toolName,
                    startTime: Date.now(),
                    element: toolCallElement
                });
                toolCallElement.setAttribute('data-call-id', callId);
                toolCallElement.dataset.callId = callId;
                toolCallElement.dataset.toolName = toolName;
            }

            // 添加到DOM
            if (this.currentMessageElement) {
                this.currentMessageElement.appendChild(toolCallElement);
            }

            this.currentToolCall = toolCallElement;
            return;
        }

        // 增加并发工具计数
        this.activeConcurrentTools++;

        // 创建工具调用元素
        const toolCallElement = this.createToolCallElement(toolName, callId);

        // 如果有 call_id，存储到 Map 中并设置状态
        if (callId) {
            // 存储元素映射
            this.toolCallMap.set(callId, toolCallElement);

            // 设置状态跟踪
            this.toolCallStates.set(callId, {
                status: 'starting',
                toolName: toolName,
                startTime: Date.now(),
                element: toolCallElement
            });

            // 设置DOM属性
            toolCallElement.setAttribute('data-call-id', callId);
            toolCallElement.dataset.callId = callId;
            toolCallElement.dataset.toolName = toolName;

            console.log(`✅ 工具映射已建立: ${toolName} -> ${callId} (活跃工具数: ${this.activeConcurrentTools})`);
        } else {
            console.warn('⚠️ 工具调用没有 call_id:', event);
        }

        // 设置为当前工具调用（用于向后兼容）
        this.currentToolCall = toolCallElement;

        // 添加到DOM
        if (this.currentMessageElement) {
            this.currentMessageElement.appendChild(toolCallElement);

            // 更新工具状态显示
            this.updateToolCallStatus(callId, 'running');

            // 强制触发重绘，确保元素立即显示
            toolCallElement.offsetHeight;

            console.log(`📍 工具元素已添加到DOM: ${toolName} (call_id: ${callId})`);
        } else {
            console.error('❌ currentMessageElement 为空，无法添加工具元素');
        }

        // 滚动到底部显示新工具
        this.scrollToBottom();
    }

    /**
     * 处理工具参数事件
     */
    handleToolArgs(event) {
        const toolName = event.tool_name || event.tool?.name;

        // 检查是否需要隐藏工具参数
        const shouldHideArgs = this.fullyHiddenTools.includes(toolName) || this.hideCallOnlyTools.includes(toolName);

        if (shouldHideArgs) {
            console.log(`🔇 ${toolName} 工具跳过参数显示`);
            return;
        }

        const toolCallElement = this.getToolCallElement(event);
        console.log('🔧 handleToolArgs 开始:', {
            tool_name: event.tool_name,
            has_tool_args: !!event.tool_args,
            tool_args: event.tool_args,
            has_element: !!toolCallElement
        });

        // 隐藏工具参数信息，不在前端显示
        if (toolCallElement && event.tool_args) {
            // 不显示工具参数，保持隐藏状态
            const argsElement = toolCallElement.querySelector('.tool-args');
            if (argsElement) {
                argsElement.style.display = 'none';
            }

            // 如果是 stream_file_operation，显示"文件按钮"，点击在侧边栏展示内容
            if (event.tool_name === 'stream_file_operation') {
                const filepath = event.tool_args?.filepath || event.tool_args?.path || '';
                const operationMode = event.tool_args?.operation_mode || event.tool_args?.mode || '文件操作';

                console.log('📂 检测到文件操作:', {
                    filepath: filepath,
                    operationMode: operationMode,
                    full_tool_args: event.tool_args
                });

                if (filepath) {
                    // 将路径保存到工具元素中
                    toolCallElement.dataset.filepath = filepath;
                    toolCallElement.dataset.operationMode = operationMode || '';

                    console.log('✅ 文件路径已保存到元素:', {
                        filepath: toolCallElement.dataset.filepath,
                        operationMode: toolCallElement.dataset.operationMode
                    });

                    this.addFileOperationButton({ filepath, operationMode, toolCallElement });
                } else {
                    console.warn('⚠️ 文件操作但没有filepath参数');
                }
            }
        }
    }

    /**
     * 处理工具结果开始事件
     */
    handleToolResultStart(event) {
        const callId = event.tool?.call_id;
        const toolName = event.tool_name || event.tool?.name || this.toolCallStates.get(callId)?.toolName || '未知工具';

        // 跳过完全隐藏和只隐藏调用框的工具的结果开始事件
        if (this.fullyHiddenTools.includes(toolName) || this.hideCallOnlyTools.includes(toolName)) {
            console.log(`🔇 ${toolName} 工具跳过结果开始显示`);
            return;
        }

        console.log(`📋 收到工具结果开始事件: ${toolName} (call_id: ${callId})`);

        const toolCallElement = this.getToolCallElement(event);
        if (toolCallElement) {
            console.log(`✅ 找到工具调用元素: ${toolName} (call_id: ${callId})`);

            let resultElement = toolCallElement.querySelector('.tool-result');
            
            if (resultElement) {
                // 显示工具结果区域
                resultElement.style.display = 'block';
                resultElement.innerHTML = '';  // 清空之前的内容
                console.log(`✅ 工具结果区域已准备就绪: ${toolName} (call_id: ${callId})`);
            } else {
                console.warn(`⚠️ 工具结果元素不存在，正在创建: ${toolName} (call_id: ${callId})`);
                // 创建缺失的结果元素
                resultElement = document.createElement('div');
                resultElement.className = 'tool-result';
                resultElement.style.display = 'block';
                toolCallElement.appendChild(resultElement);
                console.log(`🔧 已创建缺失的工具结果元素: ${toolName} (call_id: ${callId})`);
            }
            
            // 更新工具状态为正在获取结果
            this.updateToolCallStatus(callId, 'running');
            
            // 强制触发重绘
            resultElement.offsetHeight;
            
        } else {
            console.error(`❌ 找不到工具调用元素进行结果显示: ${toolName} (call_id: ${callId})`);
            console.error(`   当前toolCallMap状态:`, Array.from(this.toolCallMap.keys()));
            this.debugConcurrentToolState();
            
            // 增强的延迟查找机制
            this.retryToolElementLookup(event, 'handleToolResultStart', 3);
        }
    }

    /**
     * 处理工具结果内容事件 - 流式显示工具执行结果
     */
    handleToolResultContent(event) {
        const callId = event.tool?.call_id;
        const toolName = event.tool_name || event.tool?.name || this.toolCallStates.get(callId)?.toolName || '未知工具';

        // 只隐藏完全隐藏列表中的工具结果内容
        if (this.fullyHiddenTools.includes(toolName)) {
            console.log(`🔇 ${toolName} 工具跳过结果内容显示`);
            return;
        }

        // 对于只隐藏调用框的工具（如 ask_user），将结果作为普通文本显示
        if (this.hideCallOnlyTools.includes(toolName)) {
            console.log(`📝 ${toolName} 工具结果作为普通文本显示`);
            if (event.content && this.currentMessageElement) {
                // 在内容前后添加换行符，使其与其他内容有更好的间隔
                const contentWithNewlines = '\n' + event.content + '\n';
                // 直接追加到当前消息区域，就像 agent_content 一样
                this.appendToCurrentMessage(contentWithNewlines);
            }
            return;
        }

        console.log(`📝 收到工具结果内容事件: ${toolName} (call_id: ${callId})`);

        // 如果没有内容，跳过处理
        if (!event.content) {
            console.log(`📝 事件内容为空，跳过显示: ${toolName} (call_id: ${callId})`);
            return;
        }

        console.log(`📝 内容预览: ${event.content.substring(0, 100)}...`);
        
        // 流式显示工具执行结果
        const toolCallElement = this.getToolCallElement(event);
        if (toolCallElement) {
            console.log(`✅ 找到工具调用元素: ${toolName} (call_id: ${callId})`);
            
            let resultElement = toolCallElement.querySelector('.tool-result');
            
            // 如果结果元素不存在，创建一个
            if (!resultElement) {
                console.warn(`⚠️ 工具结果元素不存在，正在创建: ${toolName} (call_id: ${callId})`);
                resultElement = document.createElement('div');
                resultElement.className = 'tool-result';
                resultElement.style.display = 'block';
                toolCallElement.appendChild(resultElement);
                console.log(`🔧 已创建工具结果元素: ${toolName} (call_id: ${callId})`);
            } else {
                console.log(`✅ 工具结果元素已存在: ${toolName} (call_id: ${callId})`);
            }
            
            // 确保结果元素可见
            resultElement.style.display = 'block';
            
            // 格式化内容并使用innerHTML来支持换行符
            const formattedContent = this.formatTextContent(event.content);
            const beforeLength = resultElement.innerHTML.length;
            resultElement.innerHTML += formattedContent;
            const afterLength = resultElement.innerHTML.length;
            
            console.log(`📝 内容已追加: ${toolName} (call_id: ${callId}, 原长度: ${beforeLength}, 新长度: ${afterLength}, 追加: ${afterLength - beforeLength})`);

            // 如果是文件操作，实时更新侧边栏（基于上次记录的文件路径）
            if (event.tool_name === 'stream_file_operation') {
                const filepath = toolCallElement.dataset.filepath;
                if (filepath) {
                    this.updateFileContentStream(filepath, event.content);
                }
            }
            
            // 滚动到底部以显示最新内容
            this.scrollToBottom();
        } else {
            console.error(`❌ 找不到工具调用元素，无法追加结果内容: ${toolName} (call_id: ${callId})`);
            console.error(`   当前Map大小: ${this.toolCallMap.size}, Map中的call_id: [${Array.from(this.toolCallMap.keys()).join(', ')}]`);
            
            // 调试当前状态
            this.debugConcurrentToolState();
            
            // 使用增强的重试机制
            this.retryToolElementLookup(event, 'handleToolResultContent', 2);
        }
    }

    /**
     * 处理工具结果结束事件
     */
    handleToolResultEnd(event) {
        const callId = event.tool?.call_id;
        const toolName = this.toolCallStates.get(callId)?.toolName || event.tool_name || event.tool?.name || '未知工具';

        // 跳过完全隐藏和只隐藏调用框的工具的结果结束事件
        if (this.fullyHiddenTools.includes(toolName) || this.hideCallOnlyTools.includes(toolName)) {
            console.log(`🔇 ${toolName} 工具跳过结果结束显示`);
            return;
        }

        const toolCallElement = this.getToolCallElement(event);

        if (toolCallElement) {
            // 更新工具状态为完成
            this.updateToolCallStatus(callId, 'completed');

            // 减少并发工具计数
            this.activeConcurrentTools = Math.max(0, this.activeConcurrentTools - 1);

            // 保存当前完成的工具引用，用于后续的 agent_content 追加
            this.lastCompletedToolCall = toolCallElement;

            const toolName = this.toolCallStates.get(callId)?.toolName || '未知工具';
            const duration = this.toolCallStates.get(callId) ?
                Date.now() - this.toolCallStates.get(callId).startTime : 0;

            console.log(`✅ 工具执行完成: ${toolName} (call_id: ${callId}, 耗时: ${duration}ms, 剩余活跃: ${this.activeConcurrentTools})`);

            // 在工具元素中添加完成标识
            const completionBadge = document.createElement('span');
            completionBadge.className = 'tool-completion-badge';
            completionBadge.innerHTML = `<i class="fas fa-check-circle"></i> 完成 (${(duration/1000).toFixed(1)}s)`;
            completionBadge.style.cssText = `
                color: #10b981;
                font-size: 12px;
                margin-left: 8px;
                display: inline-flex;
                align-items: center;
                gap: 4px;
            `;

            const toolHeader = toolCallElement.querySelector('.tool-header');
            if (toolHeader && !toolHeader.querySelector('.tool-completion-badge')) {
                toolHeader.appendChild(completionBadge);
            }

            // 如果是文件操作工具，更新文件操作按钮状态
            if (toolName === 'stream_file_operation') {
                this.markFileOperationAsCompleted(toolCallElement);
            }

        } else {
            console.error(`❌ 找不到工具调用元素进行结束处理: call_id=${callId}, Map大小=${this.toolCallMap.size}`);
            this.debugConcurrentToolState();
        }

        // 如果当前工具调用就是刚完成的这个，清空它
        if (this.currentToolCall === toolCallElement) {
            this.currentToolCall = null;
            console.log(`🔄 清空currentToolCall: ${callId}`);
        }

        // 如果所有并发工具都完成了，显示提示
        if (this.activeConcurrentTools === 0) {
            console.log('🎉 所有并发工具调用已完成');
        }
    }

    /**
     * 标记文件操作为完成状态
     */
    markFileOperationAsCompleted(toolCallElement) {
        // 查找工具元素内的文件操作按钮
        const fileButton = toolCallElement.querySelector('.file-operation');

        if (fileButton) {
            // 添加完成状态类
            fileButton.classList.add('completed');

            // 显示准备就绪徽章
            const readyBadge = fileButton.querySelector('.file-ready-badge');
            if (readyBadge) {
                readyBadge.style.display = 'flex';
            }

            // 添加完成状态图标
            const existingStatus = fileButton.querySelector('.file-status');
            if (!existingStatus) {
                const statusDiv = document.createElement('div');
                statusDiv.className = 'file-status';
                statusDiv.innerHTML = '<i class="fas fa-check-circle"></i>';
                fileButton.appendChild(statusDiv);
            }

            console.log('📄 文件操作已标记为完成');
        }
    }

    /**
     * 根据事件获取对应的工具调用元素
     * 优先使用 call_id 从 Map 中查找，如果没有则使用 currentToolCall
     */
    getToolCallElement(event) {
        const callId = event.tool?.call_id;
        
        if (callId) {
            // 首先尝试从 Map 中获取
            if (this.toolCallMap.has(callId)) {
                const element = this.toolCallMap.get(callId);
                if (element && element.parentNode) {
                    // 元素还在 DOM 中，返回它
                    return element;
                } else {
                    // 元素已从 DOM 中移除，从 Map 中删除
                    this.toolCallMap.delete(callId);
                    console.warn('Map中的元素已不在DOM中，已删除:', callId);
                }
            }
            
            // 如果 Map 中没有，尝试通过 DOM 查找
            if (this.currentMessageElement) {
                // 尝试多种查找方式
                let toolElement = this.currentMessageElement.querySelector(`[data-call-id="${callId}"]`);
                
                // 如果第一种方式失败，尝试查找所有工具元素并匹配
                if (!toolElement) {
                    const allToolElements = this.currentMessageElement.querySelectorAll('.tool-call');
                    for (const el of allToolElements) {
                        if (el.getAttribute('data-call-id') === callId || el.dataset.callId === callId) {
                            toolElement = el;
                            break;
                        }
                    }
                }
                
                if (toolElement) {
                    // 找到后存储到 Map 中
                    this.toolCallMap.set(callId, toolElement);
                    console.log('通过DOM查找找到工具元素，call_id:', callId);
                    return toolElement;
                } else {
                    console.warn('DOM查找失败，call_id:', callId);
                    // 调试信息：显示当前所有工具元素
                    const allToolElements = this.currentMessageElement.querySelectorAll('.tool-call');
                    const existingCallIds = Array.from(allToolElements).map(el => 
                        el.getAttribute('data-call-id') || el.dataset.callId || 'no-id'
                    );
                    console.log('当前消息中所有工具元素的call_id:', existingCallIds);
                }
            } else {
                console.warn('currentMessageElement 不存在，无法查找工具元素');
            }
        } else {
            console.warn('事件没有call_id，使用后备方案');
        }
        
        // 向后兼容：如果没有 call_id 或找不到元素，使用 currentToolCall
        if (this.currentToolCall && this.currentToolCall.parentNode) {
            console.log('使用 currentToolCall 作为后备，call_id:', callId || 'none');
            return this.currentToolCall;
        }
        
        // 最后的后备方案：查找最后一个工具元素
        if (this.currentMessageElement) {
            const lastToolElement = this.currentMessageElement.querySelector('.tool-call:last-child');
            if (lastToolElement) {
                console.log('使用最后一个工具元素作为后备，call_id:', callId || 'none');
                return lastToolElement;
            }
        }
        
        console.error('所有查找方式都失败了，call_id:', callId);
        return null;
    }

    /**
     * 处理Agent运行事件
     */
    handleAgentRunning(event) {
        this.updateStatus(`执行轮次: ${event.current_round || '未知'}`, 'processing');
    }

    /**
     * 处理用户询问事件
     */
    handleAskUser(event) {
        console.log('收到用户询问事件:', event);
        
        // 显示询问内容
        if (event.content) {
            const questionDiv = document.createElement('div');
            questionDiv.className = 'user-question';
            questionDiv.innerHTML = `
                <div class="question-header">
                    <i class="fas fa-question-circle"></i>
                    <span>AI需要您的回答</span>
                </div>
                <div class="question-content">
                    ${this.escapeHtml(event.content)}
                </div>
                <div class="question-actions">
                    <input type="text" class="question-input" placeholder="请输入您的回答...">
                    <button class="question-submit" onclick="app.submitUserAnswer(this)">提交回答</button>
                </div>
            `;
            
            if (this.currentMessageElement) {
                this.currentMessageElement.appendChild(questionDiv);
            } else {
                this.elements.chatMessages.appendChild(questionDiv);
            }
            
            this.scrollToBottom();
        }
        
        this.updateStatus('等待用户回答', 'waiting');
    }

    /**
     * 处理Agent完成事件
     */
    handleAgentFinished(event) {
        this.updateStatus('执行完成', 'completed');
        this.setInputEnabled(true);

        // 添加完成提示
        if (this.currentMessageElement) {
            const completionInfo = document.createElement('div');
            completionInfo.className = 'completion-info';
            completionInfo.innerHTML = `
                <small style="color: #64748b; font-style: italic;">
                    ✅ 执行完成 (轮次: ${event.current_round || '未知'})
                    ${event.data?.execution_time ? `耗时: ${event.data.execution_time.toFixed(2)}秒` : ''}
                </small>
            `;
            this.currentMessageElement.appendChild(completionInfo);
        }
    }


    /**
     * 处理错误事件
     */
    handleError(event) {
        console.error('Agent执行错误:', event.error_message);
        this.addErrorMessage(event.content || event.error_message);
        this.updateStatus('执行失败', 'error');
        this.setInputEnabled(true);
    }

    /**
     * 添加用户消息
     */
    addUserMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        messageDiv.innerHTML = `
            <div class="message-content">
                <p>${this.escapeHtml(content)}</p>
            </div>
        `;
        this.elements.chatMessages.appendChild(messageDiv);
        this.forceScrollToBottom(); // 用户发送消息时强制滚动到底部
    }

    /**
     * 添加AI消息
     */
    addAssistantMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.innerHTML = `
            <div class="message-content">
                <div class="message-text">${content}</div>
            </div>
        `;
        this.elements.chatMessages.appendChild(messageDiv);
        this.forceScrollToBottom(); // 开始新的AI回复时强制滚动到底部
        return messageDiv.querySelector('.message-content');
    }


    /**
     * 向当前消息追加内容 - 实现流式效果
     */
    appendToCurrentMessage(content) {
        if (!this.currentMessageElement) {
            console.log('警告: currentMessageElement为空');
            return;
        }

        let textElement = this.currentMessageElement.querySelector('.message-text');
        if (!textElement) {
            textElement = document.createElement('div');
            textElement.className = 'message-text';
            this.currentMessageElement.insertBefore(textElement, this.currentMessageElement.firstChild);
            console.log('创建新的文本元素');
        }

        // 将新内容与标签缓冲区合并
        const fullContent = this.tagBuffer + content;

        console.log('💭 标签缓冲区:', JSON.stringify(this.tagBuffer), '新内容:', JSON.stringify(content), '合并后:', JSON.stringify(fullContent));

        // 处理思考内容 - 传入消息容器
        const result = this.processThinkContent(fullContent, this.currentMessageElement);

        console.log('💭 处理结果 - 普通内容:', JSON.stringify(result.processedContent), '新缓冲区:', JSON.stringify(result.tagBuffer));

        // 更新标签缓冲区
        this.tagBuffer = result.tagBuffer;

        // 追加普通内容
        if (result.processedContent) {
            console.log('📝 追加普通内容:', JSON.stringify(result.processedContent));

            // 使用文本节点追加，保持换行
            const textNode = document.createTextNode(result.processedContent);
            textElement.appendChild(textNode);
        }

        this.scrollToBottom();
    }

    /**
     * 向工具内容区域追加内容 - 实现流式效果
     */
    appendToToolContent(content) {
        if (!this.currentToolCall) {
            console.log('警告: currentToolCall为空');
            return;
        }

        let contentElement = this.currentToolCall.querySelector('.tool-content');
        if (!contentElement) {
            console.log('警告: 工具内容元素不存在');
            return;
        }

        // 将新内容与标签缓冲区合并
        const fullContent = this.tagBuffer + content;

        console.log('💭 [工具内容] 标签缓冲区:', JSON.stringify(this.tagBuffer), '新内容:', JSON.stringify(content), '合并后:', JSON.stringify(fullContent));

        // 处理思考内容 - 传入工具内容元素（而不是整个工具元素）
        const result = this.processThinkContent(fullContent, contentElement);

        console.log('💭 [工具内容] 处理结果 - 普通内容:', JSON.stringify(result.processedContent), '新缓冲区:', JSON.stringify(result.tagBuffer));

        // 更新标签缓冲区
        this.tagBuffer = result.tagBuffer;

        // 使用文本节点追加内容
        if (result.processedContent) {
            const textNode = document.createTextNode(result.processedContent);
            contentElement.appendChild(textNode);
        }

        this.scrollToBottom();
    }

    /**
     * 向工具执行后的区域追加内容 - 工具执行完成后的 agent_content
     */
    appendToToolAfterContent(content) {
        if (!this.lastCompletedToolCall) {
            console.log('警告: lastCompletedToolCall为空');
            return;
        }

        // 获取或创建工具执行后的内容区域
        let afterContentElement = this.lastCompletedToolCall.querySelector('.tool-after-content');
        if (!afterContentElement) {
            afterContentElement = document.createElement('div');
            afterContentElement.className = 'tool-after-content';
            afterContentElement.style.marginTop = '10px';
            afterContentElement.style.paddingTop = '10px';
            afterContentElement.style.borderTop = '1px solid #e5e7eb';
            this.lastCompletedToolCall.appendChild(afterContentElement);
        }

        // 将新内容与标签缓冲区合并
        const fullContent = this.tagBuffer + content;

        console.log('💭 [工具后内容] 标签缓冲区:', JSON.stringify(this.tagBuffer), '新内容:', JSON.stringify(content), '合并后:', JSON.stringify(fullContent));

        // 处理思考内容 - 传入工具后内容元素（而不是整个工具元素）
        const result = this.processThinkContent(fullContent, afterContentElement);

        console.log('💭 [工具后内容] 处理结果 - 普通内容:', JSON.stringify(result.processedContent), '新缓冲区:', JSON.stringify(result.tagBuffer));

        // 更新标签缓冲区
        this.tagBuffer = result.tagBuffer;

        // 使用文本节点追加内容
        if (result.processedContent) {
            const textNode = document.createTextNode(result.processedContent);
            afterContentElement.appendChild(textNode);
        }

        this.scrollToBottom();
    }

    /**
     * 创建工具调用元素
     */
    createToolCallElement(toolName, callId) {
        const toolDiv = document.createElement('div');
        toolDiv.className = 'tool-call';
        
        // 创建工具头部
        const headerDiv = document.createElement('div');
        headerDiv.className = 'tool-header';
        
        // 添加状态指示器
        const statusIndicator = document.createElement('span');
        statusIndicator.className = 'tool-status-indicator';
        statusIndicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        statusIndicator.style.cssText = `
            color: #3b82f6;
            margin-right: 8px;
            font-size: 12px;
        `;
        
        headerDiv.innerHTML = `
            <i class="fas fa-cog tool-icon"></i>
            <span>执行工具: ${this.escapeHtml(toolName || '未知工具')}</span>
        `;
        
        // 将状态指示器插入到头部
        headerDiv.insertBefore(statusIndicator, headerDiv.firstChild);
        
        // 创建工具参数区域（默认隐藏）
        const argsDiv = document.createElement('div');
        argsDiv.className = 'tool-args';
        argsDiv.style.display = 'none';
        
        // 创建工具内容区域
        const contentDiv = document.createElement('div');
        contentDiv.className = 'tool-content';
        
        // 创建工具结果区域（默认隐藏，但确保存在）
        const resultDiv = document.createElement('div');
        resultDiv.className = 'tool-result';
        resultDiv.style.display = 'none';
        
        // 组装元素
        toolDiv.appendChild(headerDiv);
        toolDiv.appendChild(argsDiv);
        toolDiv.appendChild(contentDiv);
        toolDiv.appendChild(resultDiv);
        
        console.log(`🔧 创建工具调用元素: ${toolName} (call_id: ${callId})`, {
            hasHeader: !!toolDiv.querySelector('.tool-header'),
            hasArgs: !!toolDiv.querySelector('.tool-args'),
            hasContent: !!toolDiv.querySelector('.tool-content'),
            hasResult: !!toolDiv.querySelector('.tool-result'),
            hasStatusIndicator: !!toolDiv.querySelector('.tool-status-indicator')
        });
        
        return toolDiv;
    }

    /**
     * 添加文件操作信息
     */
    addFileOperationButton({ filepath, operationMode, toolCallElement }) {
        const fileDiv = document.createElement('button');
        fileDiv.type = 'button';
        fileDiv.className = 'file-operation button-like';
        fileDiv.onclick = () => this.showFileContent(filepath, operationMode);

        const fileName = filepath.split('/').pop();
        const fileIcon = this.getFileIcon(fileName);

        // 根据操作模式显示不同的文本
        let modeText = operationMode || '文件操作';
        let modeIcon = '';

        switch(operationMode) {
            case 'append':
                modeText = 'append';
                modeIcon = '<i class="fas fa-plus-circle"></i> ';
                break;
            case 'write':
                modeText = 'write';
                modeIcon = '<i class="fas fa-edit"></i> ';
                break;
            case 'read':
                modeText = 'read';
                modeIcon = '<i class="fas fa-eye"></i> ';
                break;
        }

        fileDiv.innerHTML = `
            <div class="file-header">
                <i class="${fileIcon} file-icon"></i>
                <div class="file-info">
                    <div class="file-name">${this.escapeHtml(fileName)}</div>
                    <div class="file-mode">${modeIcon}${modeText}</div>
                </div>
            </div>
            <div class="file-ready-badge" style="display: none;">
                <i class="fas fa-check-circle"></i>
                <span>追加模式已准备就绪: ${this.escapeHtml(fileName)} (追加到末尾)</span>
            </div>
        `;

        // 如果提供了 toolCallElement，将文件按钮添加到工具元素中
        // 否则添加到消息区域（向后兼容）
        if (toolCallElement) {
            toolCallElement.appendChild(fileDiv);

            // 保存文件按钮引用，用于后续更新状态
            toolCallElement.dataset.fileButton = fileDiv;
        } else if (this.currentMessageElement) {
            this.currentMessageElement.appendChild(fileDiv);
        }

        return fileDiv;
    }

    /**
     * 获取文件图标
     */
    getFileIcon(fileName) {
        const ext = fileName.split('.').pop().toLowerCase();
        const iconMap = {
            'js': 'fab fa-js-square',
            'py': 'fab fa-python',
            'html': 'fab fa-html5',
            'css': 'fab fa-css3-alt',
            'json': 'fas fa-code',
            'md': 'fab fa-markdown',
            'txt': 'fas fa-file-alt',
            'pdf': 'fas fa-file-pdf',
            'doc': 'fas fa-file-word',
            'docx': 'fas fa-file-word',
            'xls': 'fas fa-file-excel',
            'xlsx': 'fas fa-file-excel'
        };
        return iconMap[ext] || 'fas fa-file';
    }

    /**
     * 显示文件内容
     */
    async showFileContent(filePath, operationMode) {
        // 更新标题
        this.elements.sidebarTitle.textContent = `${filePath.split('/').pop()} - ${operationMode || '查看'}`;

        // 打开侧边栏
        this.elements.sidebar.classList.add('open');

        // 显示文件元数据
        const fileMetadata = document.getElementById('fileMetadata');
        const fileMetadataPath = document.getElementById('fileMetadataPath');
        const fileMetadataName = document.getElementById('fileMetadataName');
        const fileMetadataMode = document.getElementById('fileMetadataMode');

        if (fileMetadata && fileMetadataPath && fileMetadataName && fileMetadataMode) {
            fileMetadata.style.display = 'block';
            fileMetadataPath.textContent = filePath;
            fileMetadataName.textContent = filePath.split('/').pop();
            fileMetadataMode.textContent = operationMode || '未知';
        }

        // 显示内容提示
        const fileContentHint = document.getElementById('fileContentHint');
        if (fileContentHint) {
            fileContentHint.style.display = 'block';
            fileContentHint.className = 'file-content-hint';
            fileContentHint.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在加载文件内容...';
        }

        // 显示内容预览区域
        const fileContentPreview = document.getElementById('fileContentPreview');
        if (fileContentPreview) {
            fileContentPreview.style.display = 'block';
        }

        // 清空并准备文件内容区域
        this.elements.fileContent.textContent = '';

        // 保存当前文件路径，用于流式更新
        this.currentFilePath = filePath;
        this.currentFileMode = operationMode;

        try {
            // 方案1：先尝试从DOM中读取已接收的内容
            const cachedContent = this.getFileContentFromToolResult(filePath);

            if (cachedContent) {
                // 如果找到了缓存内容，提取纯文本显示
                const textContent = this.extractTextFromHTML(cachedContent);
                this.elements.fileContent.textContent = textContent;

                // 更新提示为就绪状态
                if (fileContentHint) {
                    fileContentHint.className = 'file-content-hint ready';
                    fileContentHint.innerHTML = '<i class="fas fa-check-circle"></i> 文件内容已加载（来自缓存）';
                }

                console.log('📄 从DOM缓存中成功加载文件内容:', filePath);
                return;
            }

            // 方案2：如果DOM中没有内容，调用后端API读取文件
            console.log('📄 从后端API读取文件:', filePath);

            const response = await fetch(`${this.apiBaseUrl}/file/read?filepath=${encodeURIComponent(filePath)}`);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.status === 'success' && data.content) {
                // 直接显示纯文本内容
                this.elements.fileContent.textContent = data.content;

                // 更新提示为就绪状态
                if (fileContentHint) {
                    fileContentHint.className = 'file-content-hint ready';
                    fileContentHint.innerHTML = `<i class="fas fa-check-circle"></i> 文件内容已加载 (${data.size} 字符)`;
                }

                console.log('📄 从后端API成功加载文件内容:', filePath, '大小:', data.size);
            } else {
                throw new Error('Invalid response format');
            }

        } catch (error) {
            const errorContent = `加载文件失败: ${error.message}`;
            this.elements.fileContent.textContent = errorContent;

            // 更新提示为错误状态
            if (fileContentHint) {
                fileContentHint.className = 'file-content-hint error';
                fileContentHint.innerHTML = '<i class="fas fa-exclamation-circle"></i> ' + errorContent;
            }

            console.error('📄 加载文件失败:', error);
        }
    }

    /**
     * 从HTML内容中提取纯文本
     */
    extractTextFromHTML(html) {
        // 创建临时元素来解析HTML
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;

        // 获取纯文本内容
        return tempDiv.textContent || tempDiv.innerText || '';
    }

    /**
     * 从工具调用结果中获取文件内容
     */
    getFileContentFromToolResult(filePath) {
        if (!this.currentMessageElement) {
            console.log('📄 currentMessageElement 为空');
            return null;
        }

        // 查找所有包含 stream_file_operation 工具的元素
        const allToolElements = this.currentMessageElement.querySelectorAll('.tool-call');
        console.log(`📄 查找文件内容，目标路径: ${filePath}, 找到 ${allToolElements.length} 个工具元素`);

        // 遍历所有工具元素，查找匹配的文件路径
        for (const toolElement of allToolElements) {
            const toolFilePath = toolElement.dataset.filepath;
            const toolName = toolElement.dataset.toolName;

            console.log(`📄 检查工具: ${toolName}, 文件路径: ${toolFilePath}`);

            // 多种匹配策略：
            // 1. 完全匹配
            // 2. 文件名匹配（不区分路径）
            // 3. 路径结尾匹配
            const fileName = filePath.split('/').pop();
            const toolFileName = toolFilePath?.split('/').pop();

            const isMatch = toolFilePath === filePath ||
                           toolFileName === fileName ||
                           toolFilePath?.endsWith(filePath) ||
                           filePath.endsWith(toolFilePath);

            if (isMatch) {
                console.log(`📄 路径匹配成功: ${toolFilePath} ≈ ${filePath}`);

                // 找到匹配的工具元素，读取其 tool-result 内容
                const toolResult = toolElement.querySelector('.tool-result');

                if (toolResult) {
                    // 获取文本内容（innerHTML可能包含HTML标签）
                    const content = toolResult.innerHTML || toolResult.textContent;

                    if (content && content.trim()) {
                        console.log(`📄 找到文件内容，长度: ${content.length} 字符`);
                        console.log(`📄 内容预览: ${content.substring(0, 100)}...`);
                        return content;
                    } else {
                        console.log('📄 tool-result 元素存在但内容为空');
                    }
                } else {
                    console.log('📄 未找到 tool-result 元素');
                }
            }
        }

        console.log(`📄 未找到匹配的工具结果: ${filePath}`);
        return null;
    }

    /**
     * 更新文件内容流
     */
    updateFileContentStream(filePath, content) {
        // 如果侧边栏未打开，不进行更新
        if (!this.elements.sidebar.classList.contains('open')) {
            return;
        }

        // 检查当前打开的文件是否匹配
        const fileName = filePath.split('/').pop();

        // 如果当前打开的文件路径匹配，则流式追加内容
        if (this.currentFilePath === filePath || this.currentFilePath?.endsWith(fileName)) {
            console.log(`📄 流式追加内容到侧边栏: ${content.length} 字符`);

            // 直接追加纯文本内容，不进行HTML格式化
            this.elements.fileContent.textContent += content;

            // 自动滚动到底部
            const contentElement = this.elements.fileContent;
            if (contentElement) {
                contentElement.scrollTop = contentElement.scrollHeight;
            }

            // 更新内容提示
            const fileContentHint = document.getElementById('fileContentHint');
            if (fileContentHint && fileContentHint.style.display !== 'none') {
                fileContentHint.className = 'file-content-hint ready';
                fileContentHint.innerHTML = '<i class="fas fa-sync fa-spin"></i> 正在接收文件内容...';
            }
        }
    }


    /**
     * 添加错误消息
     */
    addErrorMessage(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.innerHTML = `
            <div class="message-content" style="border-color: #ef4444; background: #fef2f2;">
                <p style="color: #dc2626;">❌ ${this.escapeHtml(message)}</p>
            </div>
        `;
        this.elements.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    /**
     * 更新状态显示
     */
    updateStatus(text, type = 'ready') {
        this.elements.statusText.textContent = text;
        
        const statusDot = document.querySelector('.status-dot');
        statusDot.className = 'status-dot';
        
        switch (type) {
            case 'connecting':
                statusDot.style.background = '#f59e0b';
                break;
            case 'processing':
                statusDot.style.background = '#3b82f6';
                break;
            case 'waiting':
                statusDot.style.background = '#8b5cf6';
                break;
            case 'completed':
                statusDot.style.background = '#10b981';
                break;
            case 'error':
                statusDot.style.background = '#ef4444';
                break;
            default:
                statusDot.style.background = '#10b981';
        }
    }

    /**
     * 设置输入框启用状态
     */
    setInputEnabled(enabled) {
        this.elements.messageInput.disabled = !enabled;
        this.elements.sendButton.disabled = !enabled;
        
        if (enabled) {
            this.elements.messageInput.placeholder = "请输入您的问题或需求...";
            this.elements.messageInput.focus();
        }
    }

    /**
     * 处理滚动事件
     */
    handleScroll(e) {
        const element = e.target;
        const scrollTop = element.scrollTop;
        const scrollHeight = element.scrollHeight;
        const clientHeight = element.clientHeight;
        
        // 计算距离底部的距离
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
        
        // 检测用户是否手动向上滚动
        if (scrollTop < this.lastScrollTop && distanceFromBottom > this.scrollThreshold) {
            this.userScrolledUp = true;
            this.showScrollToBottomButton();
        } else if (distanceFromBottom <= this.scrollThreshold) {
            // 用户滚动到底部附近，重置状态
            this.userScrolledUp = false;
            this.hideScrollToBottomButton();
        }
        
        this.lastScrollTop = scrollTop;
    }

    /**
     * 智能滚动到底部 - 只在用户位于底部时才自动滚动
     */
    scrollToBottom() {
        // 如果用户手动向上滚动了，就不自动滚动到底部
        if (this.userScrolledUp) {
            return;
        }
        
        setTimeout(() => {
            this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
        }, 50);
    }

    /**
     * 强制滚动到底部 - 无论用户位置如何都滚动
     */
    forceScrollToBottom() {
        this.userScrolledUp = false;
        this.hideScrollToBottomButton();
        setTimeout(() => {
            this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
        }, 50);
    }

    /**
     * 显示滚动到底部按钮
     */
    showScrollToBottomButton() {
        if (this.scrollToBottomButton) {
            this.scrollToBottomButton.style.display = 'flex';
            return;
        }

        // 创建滚动到底部按钮
        this.scrollToBottomButton = document.createElement('button');
        this.scrollToBottomButton.className = 'scroll-to-bottom-btn';
        this.scrollToBottomButton.innerHTML = `
            <i class="fas fa-chevron-down"></i>
            <span>新消息</span>
        `;
        this.scrollToBottomButton.onclick = () => this.forceScrollToBottom();

        // 添加到聊天容器
        const chatContainer = document.querySelector('.chat-container');
        if (chatContainer) {
            chatContainer.appendChild(this.scrollToBottomButton);
        }
    }

    /**
     * 隐藏滚动到底部按钮
     */
    hideScrollToBottomButton() {
        if (this.scrollToBottomButton) {
            this.scrollToBottomButton.style.display = 'none';
        }
    }

    /**
     * 提交用户回答
     */
    async submitUserAnswer(buttonElement) {
        const questionDiv = buttonElement.closest('.user-question');
        const inputElement = questionDiv.querySelector('.question-input');
        const answer = inputElement.value.trim();
        
        if (!answer) {
            alert('请输入您的回答');
            return;
        }
        
        // 禁用输入和按钮
        inputElement.disabled = true;
        buttonElement.disabled = true;
        buttonElement.textContent = '已提交';
        
        // 这里可以发送用户回答到后端
        console.log('用户回答:', answer);
        
        // 显示用户回答
        const answerDiv = document.createElement('div');
        answerDiv.className = 'user-answer';
        answerDiv.innerHTML = `
            <div class="answer-header">
                <i class="fas fa-user"></i>
                <span>您的回答</span>
            </div>
            <div class="answer-content">
                ${this.escapeHtml(answer)}
            </div>
        `;
        
        questionDiv.appendChild(answerDiv);
        this.scrollToBottom();
        
        // 更新状态
        this.updateStatus('已收到回答，继续执行...', 'processing');
    }

    /**
     * 更新工具调用状态显示
     */
    updateToolCallStatus(callId, status) {
        if (!callId) return;
        
        const state = this.toolCallStates.get(callId);
        if (state) {
            state.status = status;
            const element = state.element;
            const statusIndicator = element?.querySelector('.tool-status-indicator');
            
            if (statusIndicator) {
                switch (status) {
                    case 'starting':
                        statusIndicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                        statusIndicator.style.color = '#f59e0b';
                        break;
                    case 'running':
                        statusIndicator.innerHTML = '<i class="fas fa-cog fa-spin"></i>';
                        statusIndicator.style.color = '#3b82f6';
                        break;
                    case 'completed':
                        statusIndicator.innerHTML = '<i class="fas fa-check-circle"></i>';
                        statusIndicator.style.color = '#10b981';
                        break;
                    case 'error':
                        statusIndicator.innerHTML = '<i class="fas fa-exclamation-circle"></i>';
                        statusIndicator.style.color = '#ef4444';
                        break;
                }
            }
        }
    }

    /**
     * 调试并发工具调用状态
     */
    debugConcurrentToolState() {
        console.log('🔍 === 并发工具调用状态调试 ===');
        console.log('活跃并发工具数:', this.activeConcurrentTools);
        console.log('toolCallMap 大小:', this.toolCallMap.size);
        console.log('toolCallStates 大小:', this.toolCallStates.size);
        
        console.log('toolCallMap 中的 keys:', Array.from(this.toolCallMap.keys()));
        console.log('toolCallStates 中的状态:');
        
        for (const [callId, state] of this.toolCallStates.entries()) {
            const hasElement = this.toolCallMap.has(callId);
            const elementInDOM = hasElement && this.toolCallMap.get(callId).parentNode;
            
            console.log(`  ${callId}: ${state.toolName} - ${state.status} (元素存在: ${hasElement}, 在DOM中: ${!!elementInDOM})`);
        }
        
        if (this.currentMessageElement) {
            const allToolElements = this.currentMessageElement.querySelectorAll('.tool-call');
            console.log('DOM 中工具元素数量:', allToolElements.length);
            
            allToolElements.forEach((el, index) => {
                const elementCallId = el.getAttribute('data-call-id') || el.dataset.callId;
                const toolName = el.dataset.toolName || '未知';
                const hasResult = !!el.querySelector('.tool-result');
                const resultVisible = hasResult ? el.querySelector('.tool-result').style.display !== 'none' : false;
                
                console.log(`  DOM元素 ${index}: ${toolName} (call_id: ${elementCallId}, 有结果: ${hasResult}, 结果可见: ${resultVisible})`);
            });
        }
        console.log('================================');
    }

    /**
     * 重试查找工具元素的机制
     */
    retryToolElementLookup(event, methodName, maxRetries = 3, currentRetry = 0) {
        const callId = event.tool?.call_id;
        const toolName = this.toolCallStates.get(callId)?.toolName || '未知工具';
        
        if (currentRetry >= maxRetries) {
            console.error(`❌ 重试${maxRetries}次后仍然找不到工具元素: ${toolName} (call_id: ${callId})`);
            // 最后尝试：创建一个新的工具元素
            this.createMissingToolElement(event);
            return;
        }
        
        const delay = Math.pow(2, currentRetry) * 50; // 指数退避：50ms, 100ms, 200ms
        console.log(`🔄 延迟${delay}ms后重试查找工具元素 (${currentRetry + 1}/${maxRetries}): ${toolName} (call_id: ${callId})`);
        
        setTimeout(() => {
            const toolCallElement = this.getToolCallElement(event);
            if (toolCallElement) {
                console.log(`✅ 重试成功找到工具元素: ${toolName} (call_id: ${callId})`);
                // 重新调用原方法
                if (this[methodName]) {
                    this[methodName](event);
                }
            } else {
                this.retryToolElementLookup(event, methodName, maxRetries, currentRetry + 1);
            }
        }, delay);
    }

    /**
     * 创建缺失的工具元素（紧急恢复机制）
     */
    createMissingToolElement(event) {
        const callId = event.tool?.call_id;
        const toolName = event.tool_name || event.tool?.name || '未知工具';
        
        console.log(`🚨 紧急创建缺失的工具元素: ${toolName} (call_id: ${callId})`);
        
        if (!this.currentMessageElement) {
            console.error('❌ currentMessageElement 不存在，无法创建工具元素');
            return;
        }
        
        // 创建新的工具元素
        const toolCallElement = this.createToolCallElement(toolName, callId);
        
        // 设置映射和状态
        if (callId) {
            this.toolCallMap.set(callId, toolCallElement);
            toolCallElement.setAttribute('data-call-id', callId);
            toolCallElement.dataset.callId = callId;
            toolCallElement.dataset.toolName = toolName;
            
            // 如果状态不存在，创建一个
            if (!this.toolCallStates.has(callId)) {
                this.toolCallStates.set(callId, {
                    status: 'running',
                    toolName: toolName,
                    startTime: Date.now(),
                    element: toolCallElement
                });
            }
        }
        
        // 添加到DOM
        this.currentMessageElement.appendChild(toolCallElement);
        
        // 添加警告标识
        const warningBadge = document.createElement('span');
        warningBadge.className = 'tool-warning-badge';
        warningBadge.innerHTML = '<i class="fas fa-exclamation-triangle"></i> 恢复';
        warningBadge.style.cssText = `
            color: #f59e0b;
            font-size: 11px;
            margin-left: 8px;
            background: #fef3c7;
            padding: 2px 6px;
            border-radius: 4px;
            display: inline-flex;
            align-items: center;
            gap: 2px;
        `;
        
        const toolHeader = toolCallElement.querySelector('.tool-header');
        if (toolHeader) {
            toolHeader.appendChild(warningBadge);
        }
        
        console.log(`🔧 紧急恢复完成: ${toolName} (call_id: ${callId})`);
        this.scrollToBottom();
    }

    /**
     * 尝试修复损坏的JSON字符串
     */
    tryFixJson(jsonStr) {
        try {
            // 常见问题1: 字符串未正确结束
            if (jsonStr.endsWith('"') && !jsonStr.endsWith('"}')) {
                // 尝试添加缺失的结束括号
                let fixed = jsonStr;
                let openBraces = 0;
                let openBrackets = 0;
                let inString = false;
                let escaped = false;
                
                for (let i = 0; i < jsonStr.length; i++) {
                    const char = jsonStr[i];
                    
                    if (escaped) {
                        escaped = false;
                        continue;
                    }
                    
                    if (char === '\\') {
                        escaped = true;
                        continue;
                    }
                    
                    if (char === '"') {
                        inString = !inString;
                        continue;
                    }
                    
                    if (!inString) {
                        if (char === '{') openBraces++;
                        else if (char === '}') openBraces--;
                        else if (char === '[') openBrackets++;
                        else if (char === ']') openBrackets--;
                    }
                }
                
                // 添加缺失的结束符
                while (openBrackets > 0) {
                    fixed += ']';
                    openBrackets--;
                }
                while (openBraces > 0) {
                    fixed += '}';
                    openBraces--;
                }
                
                return fixed;
            }
            
            // 常见问题2: 截断的字符串，尝试找到最后一个完整的对象
            const lastCompleteObject = this.findLastCompleteJson(jsonStr);
            if (lastCompleteObject) {
                return lastCompleteObject;
            }
            
        } catch (e) {
            console.warn('JSON修复尝试失败:', e.message);
        }
        
        return null;
    }
    
    /**
     * 查找最后一个完整的JSON对象
     */
    findLastCompleteJson(jsonStr) {
        // 从后往前查找，尝试找到一个完整的JSON对象
        for (let i = jsonStr.length - 1; i >= 0; i--) {
            if (jsonStr[i] === '}') {
                const candidate = jsonStr.substring(0, i + 1);
                try {
                    JSON.parse(candidate);
                    return candidate;
                } catch (e) {
                    // 继续尝试
                }
            }
        }
        return null;
    }

    /**
     * 处理思考内容 - 支持流式显示和处理被分割的标签
     * @returns {Object} { processedContent: string, tagBuffer: string }
     */
    processThinkContent(content, parentElement) {
        let processedContent = '';
        let remainingContent = content;
        let newTagBuffer = '';

        while (remainingContent.length > 0) {
            if (this.isInThinkBlock) {
                // 当前正在思考块中，查找结束标签
                const endThinkIndex = remainingContent.indexOf('</think>');
                const endThinkingIndex = remainingContent.indexOf('</thinking>');

                // 确定最近的结束标签
                let endIndex = -1;
                let endTagLength = 0;

                if (endThinkIndex !== -1 && (endThinkingIndex === -1 || endThinkIndex < endThinkingIndex)) {
                    endIndex = endThinkIndex;
                    endTagLength = '</think>'.length;
                } else if (endThinkingIndex !== -1) {
                    endIndex = endThinkingIndex;
                    endTagLength = '</thinking>'.length;
                }

                if (endIndex !== -1) {
                    // 找到结束标签，追加最后的内容并结束思考块
                    const finalContent = remainingContent.substring(0, endIndex);

                    if (finalContent && this.currentThinkElement) {
                        this.appendToThinkBlock(finalContent);
                    }

                    // 结束思考块
                    this.endThinkBlock();

                    // 继续处理结束标签后的内容
                    remainingContent = remainingContent.substring(endIndex + endTagLength);
                    continue;
                } else {
                    // 检查是否可能有不完整的结束标签
                    if (this.mightHavePartialEndTag(remainingContent)) {
                        // 保存到标签缓冲区，等待下一批数据
                        newTagBuffer = remainingContent;
                        console.log('💭 检测到不完整的结束标签，保存到缓冲区:', JSON.stringify(newTagBuffer));
                        break;
                    }

                    // 没有找到结束标签，将所有内容追加到思考块
                    this.appendToThinkBlock(remainingContent);
                    break;
                }
            } else {
                // 当前不在思考块中，查找开始标签
                const startThinkIndex = remainingContent.indexOf('<think>');
                const startThinkingIndex = remainingContent.indexOf('<thinking>');

                // 确定最近的开始标签
                let startIndex = -1;
                let startTagLength = 0;

                if (startThinkIndex !== -1 && (startThinkingIndex === -1 || startThinkIndex < startThinkingIndex)) {
                    startIndex = startThinkIndex;
                    startTagLength = '<think>'.length;
                    console.log('💭 找到 <think> 标签在位置:', startIndex);
                } else if (startThinkingIndex !== -1) {
                    startIndex = startThinkingIndex;
                    startTagLength = '<thinking>'.length;
                    console.log('💭 找到 <thinking> 标签在位置:', startIndex);
                }

                if (startIndex !== -1) {
                    // 找到开始标签，先处理之前的内容
                    const beforeThink = remainingContent.substring(0, startIndex);
                    processedContent += beforeThink;

                    // 开始新的思考块
                    this.startThinkBlock(parentElement);

                    // 继续处理开始标签后的内容
                    remainingContent = remainingContent.substring(startIndex + startTagLength);
                    continue;
                } else {
                    // 没有找到开始标签，检查是否可能有不完整的开始标签
                    if (this.mightHavePartialStartTag(remainingContent)) {
                        // 找到可能的不完整标签的位置
                        const partialTagIndex = this.findPartialTagStart(remainingContent);

                        // 保存不完整标签之前的内容
                        processedContent += remainingContent.substring(0, partialTagIndex);

                        // 将可能的不完整标签保存到缓冲区
                        newTagBuffer = remainingContent.substring(partialTagIndex);
                        console.log('💭 检测到不完整的开始标签，保存到缓冲区:', JSON.stringify(newTagBuffer));
                        break;
                    }

                    // 没有找到开始标签，返回所有剩余内容
                    processedContent += remainingContent;
                    break;
                }
            }
        }

        return {
            processedContent: processedContent,
            tagBuffer: newTagBuffer
        };
    }

    /**
     * 检查是否可能有不完整的开始标签
     */
    mightHavePartialStartTag(content) {
        // 检查是否以 < 或 <t 或 <th 等开头可能是 <think> 或 <thinking> 的前缀
        const patterns = ['<', '<t', '<th', '<thi', '<thin', '<think', '<thinking'];
        for (const pattern of patterns) {
            if (content.endsWith(pattern)) {
                return true;
            }
        }
        return false;
    }

    /**
     * 检查是否可能有不完整的结束标签
     */
    mightHavePartialEndTag(content) {
        // 检查是否以 < 或 </ 或 </t 等结尾，可能是 </think> 或 </thinking> 的前缀
        // 也要考虑换行符的情况，如 \n</think
        const patterns = ['<', '</', '</t', '</th', '</thi', '</thin', '</think', '</thinking'];
        
        // 检查直接以模式结尾的情况
        for (const pattern of patterns) {
            if (content.endsWith(pattern)) {
                return true;
            }
        }
        
        // 检查以换行符+模式结尾的情况
        for (const pattern of patterns) {
            if (content.endsWith('\n' + pattern)) {
                return true;
            }
        }
        
        // 检查其他空白字符的情况
        const whitespacePatterns = ['\r\n', '\r', ' ', '\t'];
        for (const ws of whitespacePatterns) {
            for (const pattern of patterns) {
                if (content.endsWith(ws + pattern)) {
                    return true;
                }
            }
        }
        
        return false;
    }

    /**
     * 查找可能的不完整标签开始位置
     */
    findPartialTagStart(content) {
        const patterns = ['<thinking', '<think', '<thin', '<thi', '<th', '<t', '<'];
        for (const pattern of patterns) {
            const index = content.lastIndexOf(pattern);
            if (index !== -1 && index === content.length - pattern.length) {
                return index;
            }
        }
        return content.length;
    }

    /**
     * 开始新的思考块 - 流式显示
     */
    startThinkBlock(parentElement) {
        const thinkId = 'think_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

        const thinkBlock = document.createElement('div');
        thinkBlock.className = 'think-block';
        thinkBlock.innerHTML = `
            <div class="think-header" onclick="toggleThinkContent('${thinkId}')">
                <i class="fas fa-brain think-icon"></i>
                <span class="think-label">Thinking...</span>
                <i class="fas fa-chevron-up think-toggle" id="toggle_${thinkId}"></i>
            </div>
            <div class="think-content" id="content_${thinkId}" style="display: block;">
                <div class="think-text" id="text_${thinkId}"></div>
            </div>
        `;

        // 将思考块添加到父元素
        parentElement.appendChild(thinkBlock);

        // 保存当前思考块的引用
        this.currentThinkBlock = thinkBlock;
        this.currentThinkElement = document.getElementById(`text_${thinkId}`);
        this.isInThinkBlock = true;

        console.log('💭 开始新的思考块:', thinkId);
        this.scrollToBottom();
    }

    /**
     * 追加内容到当前思考块 - 流式显示
     */
    appendToThinkBlock(content) {
        if (!this.currentThinkElement || !content) {
            return;
        }

        // 使用 textContent 来避免重新解析 HTML 导致的闪烁
        // 但这样会失去格式化，所以我们创建一个临时的文本节点来追加
        const textNode = document.createTextNode(content);
        this.currentThinkElement.appendChild(textNode);

        console.log('💭 追加思考内容:', content.substring(0, 50) + '...');
        this.scrollToBottom();
    }

    /**
     * 结束当前思考块
     */
    endThinkBlock() {
        if (this.currentThinkBlock) {
            // 保持标签为 "Thinking..."，不做任何更改
            console.log('💭 思考块结束');
        }

        // 清空当前思考块引用
        this.currentThinkBlock = null;
        this.currentThinkElement = null;
        this.isInThinkBlock = false;

        this.scrollToBottom();
    }
    
    /**
     * 切换思考内容的显示/隐藏
     */
    toggleThinkContent(thinkId) {
        const contentElement = document.getElementById(`content_${thinkId}`);
        const toggleIcon = document.getElementById(`toggle_${thinkId}`);
        
        if (contentElement && toggleIcon) {
            const isVisible = contentElement.style.display !== 'none';
            
            if (isVisible) {
                // 隐藏内容
                contentElement.style.display = 'none';
                toggleIcon.className = 'fas fa-chevron-down think-toggle';
            } else {
                // 显示内容
                contentElement.style.display = 'block';
                toggleIcon.className = 'fas fa-chevron-up think-toggle';
            }
            
            console.log('💭 切换思考内容显示:', thinkId, '现在', isVisible ? '隐藏' : '显示');
            this.scrollToBottom();
        }
    }

    /**
     * 调试工具：检查工具调用状态（保持向后兼容）
     */
    debugToolCallState(callId) {
        this.debugConcurrentToolState();
    }

    /**
     * 格式化文本内容，处理换行符和其他特殊字符
     */
    formatTextContent(text) {
        if (!text) return '';
        
        // 先进行HTML转义，防止XSS攻击
        const escaped = this.escapeHtml(text);
        
        // 处理各种特殊字符
        return escaped
            .replace(/\n/g, '<br>')           // 换行符转换为<br>
            .replace(/\t/g, '&nbsp;&nbsp;&nbsp;&nbsp;')  // 制表符转换为4个空格
            .replace(/  /g, '&nbsp;&nbsp;');  // 连续空格保持格式
    }

    /**
     * HTML转义
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * 打开文件列表侧边栏
     */
    openFileList() {
        console.log('📂 打开文件列表，session_id:', this.sessionId);

        if (!this.sessionId) {
            alert('当前没有活动的会话，请先发送消息');
            return;
        }

        // 打开侧边栏
        this.elements.sidebar.classList.add('open');

        // 显示文件列表视图
        this.showFileListView();

        // 加载文件列表
        this.loadFileList();
    }

    /**
     * 显示文件列表视图
     */
    showFileListView() {
        document.getElementById('fileListView').style.display = 'block';
        document.getElementById('fileContentView').style.display = 'none';
        document.getElementById('backButton').style.display = 'none';
        document.getElementById('sidebarTitle').textContent = '文件列表';
    }

    /**
     * 显示文件内容视图
     */
    showFileContentView(fileName) {
        document.getElementById('fileListView').style.display = 'none';
        document.getElementById('fileContentView').style.display = 'block';
        document.getElementById('backButton').style.display = 'flex';
        document.getElementById('sidebarTitle').textContent = fileName;
    }

    /**
     * 加载文件列表
     */
    async loadFileList() {
        const fileListEl = document.getElementById('fileList');
        const fileCountEl = document.getElementById('fileCount');

        try {
            // 显示加载状态
            fileCountEl.textContent = '加载中...';
            fileListEl.innerHTML = `
                <div style="text-align: center; padding: 40px; color: #64748b;">
                    <i class="fas fa-spinner fa-spin" style="font-size: 32px; margin-bottom: 12px;"></i>
                    <div>正在加载文件列表...</div>
                </div>
            `;

            console.log('📂 开始加载文件列表，session_id:', this.sessionId);

            const response = await fetch(`${this.apiBaseUrl}/file/list?session_id=${encodeURIComponent(this.sessionId)}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            console.log('📂 文件列表加载成功:', data);

            // 更新文件数量
            fileCountEl.textContent = `共 ${data.count} 个文件`;

            // 渲染文件列表
            if (data.files && data.files.length > 0) {
                fileListEl.innerHTML = data.files.map(file => {
                    const icon = this.getFileIcon(file.name);
                    const size = this.formatFileSize(file.size);
                    const time = this.formatTime(file.modified);

                    return `
                        <div class="file-item" onclick="app.showFileFromList('${this.escapeHtml(file.path)}', '${this.escapeHtml(file.name)}', ${file.size}, '${file.modified}')">
                            <div class="file-item-header">
                                <i class="${icon} file-item-icon"></i>
                                <div class="file-item-name">${this.escapeHtml(file.name)}</div>
                            </div>
                            <div class="file-item-meta">
                                <div class="file-item-size">
                                    <i class="fas fa-file"></i>
                                    <span>${size}</span>
                                </div>
                                <div class="file-item-time">
                                    <i class="fas fa-clock"></i>
                                    <span>${time}</span>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            } else {
                fileListEl.innerHTML = `
                    <div class="empty-file-list">
                        <i class="fas fa-folder-open"></i>
                        <div>暂无文件</div>
                    </div>
                `;
            }

        } catch (error) {
            console.error('📂 加载文件列表失败:', error);
            fileCountEl.textContent = '加载失败';
            fileListEl.innerHTML = `
                <div style="text-align: center; padding: 40px; color: #ef4444;">
                    <i class="fas fa-exclamation-circle" style="font-size: 32px; margin-bottom: 12px;"></i>
                    <div>加载失败: ${this.escapeHtml(error.message)}</div>
                    <button onclick="app.loadFileList()" style="margin-top: 16px; padding: 8px 16px; background: #3b82f6; color: white; border: none; border-radius: 6px; cursor: pointer;">
                        重试
                    </button>
                </div>
            `;
        }
    }

    /**
     * 从文件列表中显示文件
     */
    async showFileFromList(filePath, fileName, fileSize, modified) {
        console.log('📄 显示文件:', filePath);

        // 切换到文件内容视图
        this.showFileContentView(fileName);

        // 更新元数据
        document.getElementById('fileMetadataName').textContent = fileName;
        document.getElementById('fileMetadataSize').textContent = this.formatFileSize(fileSize);
        document.getElementById('fileMetadataModified').textContent = this.formatTime(modified);

        // 清空并显示加载状态
        this.elements.fileContent.textContent = '加载中...';

        try {
            const response = await fetch(`${this.apiBaseUrl}/file/read?filepath=${encodeURIComponent(filePath)}`);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.status === 'success' && data.content) {
                this.elements.fileContent.textContent = data.content;
                console.log('📄 文件内容加载成功，大小:', data.size);
            } else {
                throw new Error('Invalid response format');
            }

        } catch (error) {
            this.elements.fileContent.textContent = `加载失败: ${error.message}`;
            console.error('📄 加载文件内容失败:', error);
        }
    }

    /**
     * 格式化文件大小
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }

    /**
     * 格式化时间
     */
    formatTime(isoString) {
        const date = new Date(isoString);
        const now = new Date();
        const diff = now - date;
        const hours = Math.floor(diff / 3600000);

        if (hours < 1) {
            const minutes = Math.floor(diff / 60000);
            return minutes < 1 ? '刚刚' : `${minutes}分钟前`;
        } else if (hours < 24) {
            return `${hours}小时前`;
        } else {
            const days = Math.floor(hours / 24);
            if (days < 7) {
                return `${days}天前`;
            } else {
                return date.toLocaleDateString('zh-CN');
            }
        }
    }

    /**
     * 生成UUID
     */
    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    /**
     * 开始新对话
     */
    startNewConversation() {
        console.log('====== 开始新对话 ======');
        console.log('旧session_id:', this.sessionId);

        // 生成新的session_id
        this.sessionId = this.generateUUID();
        console.log('新session_id:', this.sessionId);
        console.log('=====================');

        // 清空聊天消息
        this.elements.chatMessages.innerHTML = `
            <div class="message assistant">
                <div class="message-content">
                    <p>👋 您好！我是AI深度研究助手，可以帮您进行网络搜索、内容分析、测试用例生成和代码执行等任务。请告诉我您需要什么帮助？</p>
                </div>
            </div>
        `;

        // 重置状态
        this.currentMessageElement = null;
        this.currentToolCall = null;
        this.lastCompletedToolCall = null;
        this.toolCallMap.clear();
        this.toolCallStates.clear();
        this.activeConcurrentTools = 0;
        this.dataBuffer = '';
        this.thinkBuffer = '';
        this.tagBuffer = '';
        this.currentThinkBlock = null;
        this.currentThinkElement = null;
        this.isInThinkBlock = false;

        // 关闭侧边栏
        this.elements.sidebar.classList.remove('open');

        // 更新状态
        this.updateStatus('就绪', 'ready');

        // 聚焦输入框
        this.elements.messageInput.focus();

        console.log('✅ 新对话已初始化');
    }
}

// 全局函数
function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
}

// 全局函数：返回文件列表
function showFileList() {
    console.log('🔙 返回文件列表');

    // 切换视图
    document.getElementById('fileListView').style.display = 'block';
    document.getElementById('fileContentView').style.display = 'none';
    document.getElementById('backButton').style.display = 'none';
    document.getElementById('sidebarTitle').textContent = '文件列表';

    console.log('✅ 已返回文件列表视图');
}

// 初始化应用
const app = new AIAssistantApp();
window.app = app;

// 全局思考块切换函数（与测试页面保持一致）
function toggleThinkContent(thinkId) {
    const contentElement = document.getElementById(`content_${thinkId}`);
    const toggleIcon = document.getElementById(`toggle_${thinkId}`);
    
    if (contentElement && toggleIcon) {
        const isVisible = contentElement.style.display !== 'none';
        
        if (isVisible) {
            contentElement.style.display = 'none';
            toggleIcon.className = 'fas fa-chevron-down think-toggle';
        } else {
            contentElement.style.display = 'block';
            toggleIcon.className = 'fas fa-chevron-up think-toggle';
        }
        
        console.log('💭 切换思考内容显示:', thinkId, '现在', (isVisible ? '隐藏' : '显示'));
    }
}

// 将函数绑定到全局作用域
window.toggleThinkContent = toggleThinkContent;

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', () => {
    console.log('AI助手应用已启动');
});