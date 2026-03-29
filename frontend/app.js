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
        this.fullyHiddenTools = ['artifact_write', 'terminate', 'sub_agent_run', 'planning', 'file_read'];

        // 只隐藏调用框的工具列表（结果正常显示）
        this.hideCallOnlyTools = ['ask_user'];

        // 隐藏工具框但保留功能按钮的工具（创建隐藏元素+文件按钮等）
        this.hideBoxKeepButtonTools = ['stream_file_operation'];

        // 计划相关状态
        this.activePlan = null;
        this.planStepElements = {}; // stepIndex -> DOM 元素映射

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
        this.apiBaseUrl = 'http://localhost:1234/api/v1';

        // 会话ID：每个对话框维持一个session_id
        this.sessionId = this.generateUUID();
        console.log('初始化会话ID:', this.sessionId);

        // 初始化
        this.initializeElements();
        this.bindEvents();
        this.setupAutoResize();
        this.initMarkdown();
    }

    /**
     * 初始化Markdown渲染器
     */
    initMarkdown() {
        // marked v15 UMD模式: window.marked 是模块对象，实际函数在 window.marked.marked
        if (typeof marked !== 'undefined') {
            const markedFn = marked.marked || marked;
            if (typeof markedFn.use === 'function') {
                markedFn.use({ breaks: true, gfm: true });
            } else if (typeof markedFn.setOptions === 'function') {
                markedFn.setOptions({ breaks: true, gfm: true });
            }
            // 保存解析函数的引用
            this._markedParse = (typeof markedFn.parse === 'function') ? markedFn.parse.bind(markedFn)
                              : (typeof markedFn === 'function') ? markedFn : null;
            console.log('✅ Markdown渲染器已初始化, parse函数:', !!this._markedParse);
        } else {
            console.warn('⚠️ marked.js 未加载，将使用纯文本显示');
            this._markedParse = null;
        }
    }

    /**
     * 渲染Markdown文本为HTML
     */
    renderMarkdown(text) {
        if (!text) return '';
        if (this._markedParse) {
            try {
                return this._markedParse(text);
            } catch (e) {
                console.error('Markdown渲染失败:', e);
            }
        }
        // Fallback: 纯文本渲染
        return this.escapeHtml(text).replace(/\n/g, '<br>');
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
        console.log('🔗 绑定事件监听器...');

        if (!this.elements.sendButton) {
            console.error('❌ sendButton 元素不存在');
        } else {
            console.log('✅ sendButton 已绑定');
            this.elements.sendButton.addEventListener('click', () => {
                console.log('🖱️ 点击发送按钮');
                this.sendMessage();
            });
        }

        if (!this.elements.messageInput) {
            console.error('❌ messageInput 元素不存在');
        } else {
            console.log('✅ messageInput 已绑定');
            // 输入框回车发送
            this.elements.messageInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    console.log('⌨️ 按下回车键');
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        if (!this.elements.chatMessages) {
            console.error('❌ chatMessages 元素不存在');
        } else {
            console.log('✅ chatMessages 已绑定');
            // 聊天区域滚动事件监听
            this.elements.chatMessages.addEventListener('scroll', (e) => {
                this.handleScroll(e);
            });
        }
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
        console.log('🚀 sendMessage 被调用');
        console.log('📝 消息内容:', message);
        console.log('📌 elements:', this.elements);

        if (!message) {
            console.log('⚠️ 消息为空，返回');
            return;
        }

        console.log('📤 发送消息:', message, '连接状态:', this.isConnected);

        // 如果AI正在执行中，不允许发送新消息
        if (this.isConnected) {
            console.log('⚠️ AI正在执行中，无法发送新消息');
            alert('请等待当前任务完成后再发送新消息');
            return;
        }

        console.log('✅ 开始发送消息流程');

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
            console.error('❌ 发送消息失败:', error);
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
        // 处理并行分组标记
        if (event.data?.parallel_group && this.currentMessageElement) {
            if (event.data.parallel_group === 'start') {
                const count = event.data.count || 0;
                const tasks = event.data.tasks || [];

                // SUMMARY_REPORT 不进并行卡片，直接显示在主对话区
                const parallelTasks = tasks.filter(t => t.agent_name !== 'SUMMARY_REPORT');
                const summaryTasks = tasks.filter(t => t.agent_name === 'SUMMARY_REPORT');

                // 如果只有 SUMMARY_REPORT，不创建并行分组
                if (parallelTasks.length === 0) {
                    this._parallelCallIds = new Set();
                    this._parallelTotal = 0;
                    this._parallelCompleted = 0;
                    return;
                }

                const groupDiv = document.createElement('div');
                groupDiv.className = 'parallel-group';

                // 为每个并行任务预创建折叠卡片
                let cardsHtml = '';
                parallelTasks.forEach((t, idx) => {
                    const taskId = t.call_id || `parallel_${idx}`;
                    const agentName = this.escapeHtml(t.agent_name || '');
                    const taskDesc = this.escapeHtml(t.task || '');
                    cardsHtml += `
                        <div class="parallel-task-card" data-parallel-call-id="${taskId}" id="ptask_${taskId}">
                            <div class="parallel-task-header" onclick="toggleParallelTask('${taskId}')">
                                <span class="parallel-task-status"><i class="fas fa-spinner fa-spin"></i></span>
                                <span class="parallel-task-name">${agentName}</span>
                                <span class="parallel-task-desc">${taskDesc}</span>
                                <i class="fas fa-chevron-down parallel-task-toggle" id="ptoggle_${taskId}"></i>
                            </div>
                            <div class="parallel-task-body" id="pbody_${taskId}" style="display: none;"></div>
                        </div>
                    `;
                });

                groupDiv.innerHTML = `
                    <div class="parallel-group-header">
                        <i class="fas fa-layer-group"></i>
                        <span>并行执行 ${parallelTasks.length} 个子任务</span>
                        <span class="parallel-group-progress" id="pg_progress">0/${parallelTasks.length} 完成</span>
                    </div>
                    ${cardsHtml}
                `;
                this.currentMessageElement.appendChild(groupDiv);
                this._currentParallelGroup = groupDiv;
                this._parallelCallIds = new Set(parallelTasks.map(t => t.call_id).filter(Boolean));
                this._parallelTaskDescMap = {};
                // 改进：改用数组来追踪同一个并行任务的多个文件操作
                // 结构：parallelCallId → [{ toolCallId, filepath, startTime }, ...]
                this._parallelActiveFiles = {}; // 替代 _parallelActiveFile
                this._parallelCallIdToStepIndex = {}; // parallelCallId → stepIndex (预计算映射)
                parallelTasks.forEach(t => {
                    if (t.call_id && t.task) {
                        this._parallelTaskDescMap[t.call_id] = t.task;
                    }
                });
                // 预计算: 将每个并行任务映射到对应的计划步骤
                if (this.activePlan) {
                    const usedStepIndices = new Set();
                    parallelTasks.forEach(t => {
                        if (!t.call_id) return;
                        const taskDesc = t.task || '';
                        const agentType = t.agent_name || '';
                        let bestMatch = null;
                        let bestScore = 0;
                        for (const group of this.activePlan.groups) {
                            for (const step of group.steps) {
                                if (usedStepIndices.has(step.index)) continue;
                                let score = 0;
                                // 文本完全包含匹配
                                if (taskDesc && step.text) {
                                    if (taskDesc.includes(step.text) || step.text.includes(taskDesc)) {
                                        score = Math.min(taskDesc.length, step.text.length) * 2;
                                    } else {
                                        // 模糊匹配：共有关键词
                                        const keywords = taskDesc.split(/[\s，、,。]+/).filter(k => k.length > 1);
                                        const matched = keywords.filter(k => step.text.includes(k));
                                        if (matched.length > 0) {
                                            score = matched.join('').length;
                                        }
                                    }
                                }
                                // agent类型匹配加分
                                if (agentType && step.type && agentType.toUpperCase().includes(step.type.toUpperCase())) {
                                    score += 10;
                                }
                                if (score > bestScore) {
                                    bestScore = score;
                                    bestMatch = step;
                                }
                            }
                        }
                        if (bestMatch) {
                            this._parallelCallIdToStepIndex[t.call_id] = bestMatch.index;
                            usedStepIndices.add(bestMatch.index);
                        }
                    });
                    console.log('📋 并行任务→步骤映射:', this._parallelCallIdToStepIndex);

                    // 自动将匹配的步骤标记为 in_progress
                    for (const stepIndex of Object.values(this._parallelCallIdToStepIndex)) {
                        if (this.planStepElements?.[stepIndex]) {
                            const stepEl = this.planStepElements[stepIndex];
                            stepEl.className = `plan-step in_progress`;
                            const statusSpan = stepEl.querySelector('.step-status');
                            if (statusSpan) {
                                statusSpan.className = 'step-status in_progress';
                                statusSpan.innerHTML = this._stepStatusIcon('in_progress');
                            }
                        }
                        // 同步更新 activePlan 中的状态
                        if (this.activePlan) {
                            const step = this._findStepByIndex(stepIndex);
                            if (step) step.status = 'in_progress';
                        }
                    }
                }
                this._parallelCompleted = 0;
                this._parallelTotal = parallelTasks.length;
            } else if (event.data.parallel_group === 'end') {
                if (this._currentParallelGroup) {
                    const footer = document.createElement('div');
                    footer.className = 'parallel-group-footer';
                    footer.innerHTML = '<i class="fas fa-check-circle"></i> 并行任务全部完成';
                    this._currentParallelGroup.appendChild(footer);

                    const progress = this._currentParallelGroup.querySelector('.parallel-group-progress');
                    if (progress) progress.textContent = `${this._parallelTotal}/${this._parallelTotal} 完成`;

                    this._currentParallelGroup = null;
                    // 不清空 _parallelCallIds：tool_result_end 事件可能在 group end 之后到达
                    // _parallelCallIds 会在新的 parallel_group start 或 startNewConversation 时重置
                }
            }
            return;
        }

        // 并行子任务内容路由 - 通过 parallel_call_id 定位到正确的折叠卡片
        const parallelCallId = event.data?.parallel_call_id;
        if (parallelCallId && this._parallelCallIds?.has(parallelCallId)) {
            if (event.content) {
                // 改进：追踪活跃的文件操作工具 call_id，而不仅仅是最后一个
                const activeFilePath = this._getCurrentFilePathForParallelTask(parallelCallId);

                const body = document.getElementById(`pbody_${parallelCallId}`);
                if (body) {
                    // 每个并行子任务独立维护 tagBuffer 和 think 状态
                    if (body._tagBuffer === undefined) body._tagBuffer = '';
                    if (body._thinkState === undefined) {
                        body._thinkState = {
                            isInThinkBlock: false,
                            currentThinkBlock: null,
                            currentThinkElement: null
                        };
                    }

                    const fullContent = body._tagBuffer + event.content;
                    const result = this._processThinkContentIsolated(fullContent, body, body._thinkState);
                    body._tagBuffer = result.tagBuffer;

                    // 文件预览只写入过滤后的内容（不含 think 块）
                    if (activeFilePath && result.processedContent) {
                        this.updateFileContentStream(activeFilePath, result.processedContent);
                    }

                    if (result.processedContent) {
                        // 取 body 的最后一个子元素：如果是 .parallel-task-text 则继续追加，
                        // 否则说明中间插入了工具调用或 think 块，需要创建新的文本块保证顺序正确
                        let textEl = body.lastElementChild;
                        if (!textEl || !textEl.classList.contains('parallel-task-text')) {
                            textEl = document.createElement('div');
                            textEl.className = 'parallel-task-text';
                            textEl._textBuffer = '';
                            body.appendChild(textEl);
                        }
                        if (textEl._textBuffer === undefined) textEl._textBuffer = '';
                        textEl._textBuffer += result.processedContent;
                        textEl.innerHTML = this.renderMarkdown(textEl._textBuffer);
                    }
                }
            }
            this.scrollToBottom();
            return;
        }

        if (event.content && this.currentMessageElement) {
            const routeParallelId = event.data?.parallel_call_id;

            // 非并行路径也同步文件预览（如 SUMMARY_REPORT 的文件写入）
            if (routeParallelId) {
                const currentFile = this._getCurrentFilePathForParallelTask(routeParallelId);
                if (currentFile) {
                    this.updateFileContentStream(currentFile, event.content);
                }
            }

            if (this.currentToolCall) {
                this.appendToToolContent(event.content);
            } else if (this.lastCompletedToolCall) {
                this.appendToToolAfterContent(event.content);
            } else {
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

        // 标记：自上次内容输出后有工具调用介入
        this._hadToolSinceLastContent = true;

        // 并行任务的子工具调用 → 路由到折叠卡片内部
        const parallelCallId = event.data?.parallel_call_id;
        if (parallelCallId && this._parallelCallIds?.has(parallelCallId)) {
            // 需要隐藏但仍需跟踪状态的工具（如 stream_file_operation）
            if (this.hideBoxKeepButtonTools.includes(toolName)) {
                const toolDiv = this.createToolCallElement(toolName, callId);
                toolDiv.style.display = 'none';
                if (callId) {
                    this.toolCallMap.set(callId, toolDiv);
                    this.toolCallStates.set(callId, {
                        status: 'starting', toolName, startTime: Date.now(), element: toolDiv
                    });
                    toolDiv.setAttribute('data-call-id', callId);
                    toolDiv.dataset.callId = callId;
                    toolDiv.dataset.toolName = toolName;
                    toolDiv.dataset.parallelCallId = parallelCallId;
                }
                return;
            }
            if (this.fullyHiddenTools.includes(toolName)) {
                return;
            }
            const body = document.getElementById(`pbody_${parallelCallId}`);
            if (body) {
                const toolDiv = this.createToolCallElement(toolName, callId);

                if (callId) {
                    this.toolCallMap.set(callId, toolDiv);
                    this.toolCallStates.set(callId, {
                        status: 'starting', toolName, startTime: Date.now(), element: toolDiv
                    });
                    toolDiv.setAttribute('data-call-id', callId);
                    toolDiv.dataset.callId = callId;
                    toolDiv.dataset.toolName = toolName;
                }

                // 查找或创建当前工具组 — 按内容流顺序分组
                let toolGroup = body.lastElementChild;
                if (!toolGroup || !toolGroup.classList.contains('parallel-tool-group')) {
                    // 上一个元素不是工具组（可能是文本块或think块），创建新的折叠工具组
                    toolGroup = document.createElement('div');
                    toolGroup.className = 'parallel-tool-group';
                    toolGroup._toolCount = 0;

                    const toggleBtn = document.createElement('button');
                    toggleBtn.className = 'parallel-tool-toggle-btn';
                    toggleBtn.innerHTML = '📋 显示工具细节 (1)';
                    toggleBtn.dataset.expanded = 'false';
                    toggleBtn.onclick = (e) => {
                        e.stopPropagation();
                        const expand = toggleBtn.dataset.expanded === 'false';
                        toggleBtn.dataset.expanded = expand ? 'true' : 'false';
                        toggleBtn.innerHTML = expand
                            ? `🔽 隐藏工具细节 (${toolGroup._toolCount})`
                            : `📋 显示工具细节 (${toolGroup._toolCount})`;
                        const container = toolGroup.querySelector('.tool-group-container');
                        if (container) container.style.display = expand ? 'block' : 'none';
                    };
                    toolGroup._toggleBtn = toggleBtn;
                    toolGroup.appendChild(toggleBtn);

                    const container = document.createElement('div');
                    container.className = 'tool-group-container';
                    container.style.display = 'none';
                    toolGroup.appendChild(container);

                    body.appendChild(toolGroup);
                }

                // 将工具添加到当前组的容器中
                const container = toolGroup.querySelector('.tool-group-container');
                container.appendChild(toolDiv);
                toolGroup._toolCount = (toolGroup._toolCount || 0) + 1;
                // 更新按钮上的计数
                const btn = toolGroup._toggleBtn;
                if (btn) {
                    const expanded = btn.dataset.expanded === 'true';
                    btn.innerHTML = expanded
                        ? `🔽 隐藏工具细节 (${toolGroup._toolCount})`
                        : `📋 显示工具细节 (${toolGroup._toolCount})`;
                }

                this.currentToolCall = toolDiv;
                this.updateToolCallStatus(callId, 'running');
            }
            return;
        }

        console.log(`🚀 工具调用开始: ${toolName} (call_id: ${callId})`);

        // 重置思考块状态，确保每个工具调用独立
        if (this.isInThinkBlock) {
            this.endThinkBlock();
        }
        this.tagBuffer = '';

        // 检查是否需要隐藏工具调用框
        const shouldHideCall = this.fullyHiddenTools.includes(toolName) || this.hideCallOnlyTools.includes(toolName) || this.hideBoxKeepButtonTools.includes(toolName);

        if (shouldHideCall) {
            console.log(`🔇 ${toolName} 工具不显示调用框`);

            // 对于只隐藏调用框的工具（如 ask_user），完全不创建工具元素
            // 这样结果会直接显示为普通文本
            if (this.hideCallOnlyTools.includes(toolName)) {
                console.log(`✅ ${toolName} 工具完全跳过DOM创建，结果将作为普通文本显示`);
                // 不创建任何元素，直接返回
                return;
            }

            // 对于完全隐藏的工具和隐藏框但保留按钮的工具，创建隐藏元素用于状态跟踪
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

            // 判断是否应设置 currentToolCall（会拦截后续 AGENT_CONTENT）
            // 1. sub_agent_run 不设置，其子 agent 内容直接显示在主对话区
            // 2. 带 parallel_call_id 的子工具不设置（属于并行子 agent 内部工具）
            // 3. hideBoxKeepButtonTools 不设置（隐藏工具不应拦截内容流）
            const eventParallelId = event.data?.parallel_call_id;
            const isChildOfParallelAgent = !!eventParallelId;
            if (toolName === 'sub_agent_run') {
                this.lastCompletedToolCall = null;
            } else if (!isChildOfParallelAgent && !this.hideBoxKeepButtonTools.includes(toolName)) {
                this.currentToolCall = toolCallElement;
            }
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

        // 添加到DOM（如果有并行分组容器则添加到分组中）
        const parentElement = this._currentParallelGroup || this.currentMessageElement;
        if (parentElement) {
            parentElement.appendChild(toolCallElement);

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
            // sub_agent_run：提取 agent_name/task，标记对应计划步骤为 in_progress
            if (toolName === 'sub_agent_run' && event.tool_args && this.activePlan) {
                const agentName = event.tool_args.agent_name || '';
                const taskDesc = event.tool_args.task || '';
                const parallelCallId = event.data?.parallel_call_id;
                // 仅处理不在并行组中的 sub_agent_run（如被过滤的 SUMMARY_REPORT）
                if (parallelCallId && !this._parallelCallIds?.has(parallelCallId)) {
                    this._markStepInProgressByMatch(agentName, taskDesc);
                }
            }
            return;
        }

        // hideBoxKeepButtonTools: 工具框隐藏但仍需处理参数（如文件按钮）
        if (this.hideBoxKeepButtonTools.includes(toolName)) {
            if (toolName === 'stream_file_operation' && event.tool_args) {
                const toolCallElement = this.getToolCallElement(event);
                if (toolCallElement) {
                    const filepath = event.tool_args?.filepath || event.tool_args?.path || '';
                    const operationMode = event.tool_args?.operation_mode || event.tool_args?.mode || '文件操作';
                    const parallelCallId = event.data?.parallel_call_id;
                    if (filepath) {
                        toolCallElement.dataset.filepath = filepath;
                        toolCallElement.dataset.operationMode = operationMode || '';
                        this.addFileOperationButton({ filepath, operationMode, toolCallElement, parallelCallId });
                        // 记录并行子任务的活跃文件写入，支持多个文件操作
                        if (parallelCallId) {
                            const toolCallId = event.tool?.call_id;
                            if (!this._parallelActiveFiles) this._parallelActiveFiles = {};
                            if (!this._parallelActiveFiles[parallelCallId]) this._parallelActiveFiles[parallelCallId] = [];
                            // 添加到活跃文件列表（最后一个是"当前"的）
                            this._parallelActiveFiles[parallelCallId].push({
                                toolCallId,
                                filepath,
                                startTime: Date.now()
                            });
                        }
                    }
                }
            }
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

                    const parallelCallId = event.data?.parallel_call_id;
                    this.addFileOperationButton({ filepath, operationMode, toolCallElement, parallelCallId });
                    // 记录并行子任务的活跃文件写入，支持多个文件操作
                    if (parallelCallId) {
                        const toolCallId = event.tool?.call_id;
                        if (!this._parallelActiveFiles) this._parallelActiveFiles = {};
                        if (!this._parallelActiveFiles[parallelCallId]) this._parallelActiveFiles[parallelCallId] = [];
                        // 添加到活跃文件列表
                        this._parallelActiveFiles[parallelCallId].push({
                            toolCallId,
                            filepath,
                            startTime: Date.now()
                        });
                    }
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

        // 对于隐藏工具，初始化结果内容追踪
        if (this.fullyHiddenTools.includes(toolName)) {
            const toolState = this.toolCallStates.get(callId);
            if (toolState) {
                toolState.resultContent = '';  // 初始化结果内容
            }
        }

        // 跳过完全隐藏和只隐藏调用框的工具的结果开始事件
        if (this.fullyHiddenTools.includes(toolName) || this.hideCallOnlyTools.includes(toolName) || this.hideBoxKeepButtonTools.includes(toolName)) {
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
                resultElement._textBuffer = '';  // 重置Markdown缓冲区
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

        // 对于完全隐藏的工具（如 planning、mark_step），保存结果内容但不显示
        if (this.fullyHiddenTools.includes(toolName)) {
            console.log(`🔇 ${toolName} 工具结果已记录但不显示`);
            if (event.content) {
                const toolState = this.toolCallStates.get(callId);
                if (toolState) {
                    toolState.resultContent = (toolState.resultContent || '') + event.content;
                }
            }
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

        // 对于隐藏框但保留按钮的工具（如 stream_file_operation），跳过工具状态消息
        // 真正的文件内容通过 handleAgentContent → _parallelActiveFile 路径写入
        if (this.hideBoxKeepButtonTools.includes(toolName)) {
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

            // 初始化缓冲区
            if (resultElement._textBuffer === undefined) {
                resultElement._textBuffer = '';
            }

            // 累积内容并渲染Markdown
            resultElement._textBuffer += event.content;
            resultElement.innerHTML = this.renderMarkdown(resultElement._textBuffer);

            console.log(`📝 内容已渲染: ${toolName} (call_id: ${callId})`);

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

        // 并行任务的父工具完成 → 更新折叠卡片状态
        const parallelCallId = event.data?.parallel_call_id;
        if (parallelCallId && this._parallelCallIds?.has(parallelCallId)) {
            // 只有父级 sub_agent_run 自身完成时（callId === parallelCallId）才更新卡片状态和进度
            // 子任务内部的工具调用（callId !== parallelCallId）不计入进度
            if (callId === parallelCallId) {
                const card = document.getElementById(`ptask_${parallelCallId}`);
                if (card) {
                    const statusEl = card.querySelector('.parallel-task-status');
                    if (statusEl) statusEl.innerHTML = '<i class="fas fa-check-circle" style="color:#10b981"></i>';
                    card.classList.add('completed');

                    // 子任务完成时，标记该子任务关联的所有文件为完成
                    this._markParallelTaskFilesCompleted(parallelCallId);

                    // 更新进度（group 可能已 end，通过 card 向上查找 parallel-group）
                    this._parallelCompleted = (this._parallelCompleted || 0) + 1;
                    const group = this._currentParallelGroup || card.closest('.parallel-group');
                    if (group) {
                        const progress = group.querySelector('.parallel-group-progress');
                        if (progress) progress.textContent = `${this._parallelCompleted}/${this._parallelTotal} 完成`;
                    }
                }
            }
            // 清理当前工具引用
            if (this.currentToolCall) this.currentToolCall = null;
            return;
        }

        // 跳过完全隐藏和只隐藏调用框的工具的结果结束事件
        if (this.fullyHiddenTools.includes(toolName) || this.hideCallOnlyTools.includes(toolName) || this.hideBoxKeepButtonTools.includes(toolName)) {
            console.log(`🔇 ${toolName} 工具跳过结果结束显示`);

            // 特殊处理：planning 和 mark_step 工具
            if (toolName === 'planning' || toolName === 'mark_step') {
                // 获取工具结果内容（可能被隐藏，但内容还在状态中）
                const toolState = this.toolCallStates.get(callId);
                if (toolState && toolState.resultContent) {
                    // 解析计划
                    this.activePlan = this.parsePlanFromMarkdown(toolState.resultContent);
                    this.renderPlanPanel();

                    // 打开侧边栏并显示计划视图
                    if (this.elements.sidebar) {
                        this.elements.sidebar.classList.add('open');
                    }
                    this.showSidebarView('plan');

                    console.log('📋 计划已加载到侧边栏');
                }
            }

            // stream_file_operation 的 TOOL_RESULT_END 不代表文件写完
            // 实际文件内容在后续 LLM 回合通过 write_chunk 持续写入
            // 文件完成标记延迟到父级 sub_agent_run 完成时处理
            if (toolName === 'stream_file_operation') {
                // 不做任何操作，等父级 sub_agent_run 完成时统一标记
                console.log(`📝 stream_file_operation TOOL_RESULT_END (延迟标记完成)`);
            }

            // 非并行的 sub_agent_run 完成时（如 SUMMARY_REPORT），标记其关联文件完成
            if (toolName === 'sub_agent_run') {
                const pcId = event.data?.parallel_call_id;
                if (!pcId || !this._parallelCallIds?.has(pcId)) {
                    // 非并行路径：标记所有关联的 stream_file_operation 文件为完成
                    for (const [cid, el] of this.toolCallMap.entries()) {
                        if (el && el.dataset?.toolName === 'stream_file_operation') {
                            // 非并行 sub_agent_run 没有 parallelCallId，标记所有未完成的文件
                            if (!el.classList.contains('file-completed')) {
                                this.markFileOperationAsCompleted(el);
                            }
                        }
                    }
                    // 清除所有非并行的活跃文件映射
                    if (this._parallelActiveFiles) {
                        for (const key of Object.keys(this._parallelActiveFiles)) {
                            if (!this._parallelCallIds?.has(key)) {
                                delete this._parallelActiveFiles[key];
                            }
                        }
                    }
                    // 标记对应计划步骤的文件 spinner 完成
                    if (this.planStepElements) {
                        for (const stepEl of Object.values(this.planStepElements)) {
                            if (stepEl.classList.contains('in_progress')) {
                                const spinners = stepEl.querySelectorAll('.plan-file-status:not(.completed)');
                                spinners.forEach(s => {
                                    s.className = 'plan-file-status completed';
                                    s.innerHTML = '<i class="fas fa-check-circle"></i>';
                                });
                            }
                        }
                    }
                }
            }
            // 清理可能的 currentToolCall 残留
            if (this.currentToolCall) {
                const hiddenEl = this.getToolCallElement(event);
                if (hiddenEl && this.currentToolCall === hiddenEl) {
                    this.currentToolCall = null;
                }
            }
            return;
        }

        const toolCallElement = this.getToolCallElement(event);

        if (toolCallElement) {
            // 重置思考块状态，防止跨工具调用泄漏
            if (this.isInThinkBlock) {
                this.endThinkBlock();
            }
            this.tagBuffer = '';

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
        // 更新计划面板中的文件状态
        const statusEl = toolCallElement._planFileStatus;
        const downloadBtn = toolCallElement._planDownloadBtn;

        if (statusEl) {
            statusEl.className = 'plan-file-status completed';
            statusEl.innerHTML = '<i class="fas fa-check-circle"></i>';
        }
        if (downloadBtn) {
            downloadBtn.classList.add('ready');
        }

        toolCallElement.classList.add('file-completed');
        console.log('📄 文件操作已标记为完成');
    }

    /**
     * 并行子任务完成时，标记其关联的所有文件为完成状态
     */
    _markParallelTaskFilesCompleted(parallelCallId) {
        // 遍历 toolCallMap，找到属于该并行子任务的 stream_file_operation 工具
        for (const [callId, el] of this.toolCallMap.entries()) {
            if (el && el.dataset?.toolName === 'stream_file_operation' && el.dataset?.parallelCallId === parallelCallId) {
                this.markFileOperationAsCompleted(el);
            }
        }
        // 也通过 step 文件容器查找仍在转圈的文件图标
        const stepIndex = this._parallelCallIdToStepIndex?.[parallelCallId];
        if (stepIndex !== undefined && this.planStepElements?.[stepIndex]) {
            const stepEl = this.planStepElements[stepIndex];
            const spinners = stepEl.querySelectorAll('.plan-file-status:not(.completed)');
            spinners.forEach(statusEl => {
                statusEl.className = 'plan-file-status completed';
                statusEl.innerHTML = '<i class="fas fa-check-circle"></i>';
            });
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

        // 并行子任务的错误 → 显示在卡片内，不影响全局状态
        const parallelCallId = event.data?.parallel_call_id;
        if (parallelCallId && this._parallelCallIds?.has(parallelCallId)) {
            const body = document.getElementById(`pbody_${parallelCallId}`);
            if (body) {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'parallel-task-text message-text';
                errorDiv.style.color = '#dc2626';
                errorDiv.textContent = `❌ 执行失败: ${event.error_message || '未知错误'}`;
                body.appendChild(errorDiv);
            }
            return;
        }

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
     * 向当前消息追加内容 - Markdown流式渲染
     */
    appendToCurrentMessage(content) {
        if (!this.currentMessageElement) {
            console.log('警告: currentMessageElement为空');
            return;
        }

        // 查找可复用的文本元素：必须是 currentMessageElement 的最后一个直接子 .message-text
        // 且后面没有并行组、工具等其他元素
        let textElement = null;
        const lastChild = this.currentMessageElement.lastElementChild;
        if (lastChild && lastChild.classList.contains('message-text')) {
            textElement = lastChild;
        }
        if (!textElement) {
            textElement = document.createElement('div');
            textElement.className = 'message-text';
            textElement._textBuffer = '\n\n';
            this.currentMessageElement.appendChild(textElement);
        } else if (this._hadToolSinceLastContent && textElement._textBuffer) {
            // 复用已有文本块，但中间有工具调用介入，追加换行分隔
            textElement._textBuffer += '\n\n';
        }
        this._hadToolSinceLastContent = false;

        // 初始化缓冲区
        if (textElement._textBuffer === undefined) {
            textElement._textBuffer = '';
        }

        // 将新内容与标签缓冲区合并
        const fullContent = this.tagBuffer + content;

        console.log('💭 标签缓冲区:', JSON.stringify(this.tagBuffer), '新内容:', JSON.stringify(content), '合并后:', JSON.stringify(fullContent));

        // 处理思考内容 - 传入消息容器
        const result = this.processThinkContent(fullContent, this.currentMessageElement);

        console.log('💭 处理结果 - 普通内容:', JSON.stringify(result.processedContent), '新缓冲区:', JSON.stringify(result.tagBuffer));

        // 更新标签缓冲区
        this.tagBuffer = result.tagBuffer;

        // 累积内容并渲染Markdown
        if (result.processedContent) {
            console.log('📝 追加普通内容:', JSON.stringify(result.processedContent));
            textElement._textBuffer += result.processedContent;
            textElement.innerHTML = this.renderMarkdown(textElement._textBuffer);
        }

        this.scrollToBottom();
    }

    /**
     * 向工具内容区域追加内容 - Markdown流式渲染
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

        // 处理思考内容 - 传入工具内容元素
        const result = this.processThinkContent(fullContent, contentElement);

        // 更新标签缓冲区
        this.tagBuffer = result.tagBuffer;

        // 获取或创建文本子元素（与think块分离）
        let textElement = contentElement.querySelector('.tool-content-text');
        if (!textElement) {
            textElement = document.createElement('div');
            textElement.className = 'tool-content-text';
            textElement._textBuffer = '';
            contentElement.appendChild(textElement);
        }
        if (textElement._textBuffer === undefined) {
            textElement._textBuffer = '';
        }

        // 累积内容并渲染Markdown
        if (result.processedContent) {
            textElement._textBuffer += result.processedContent;
            textElement.innerHTML = this.renderMarkdown(textElement._textBuffer);
        }

        this.scrollToBottom();
    }

    /**
     * 向工具执行后的区域追加内容 - Markdown流式渲染
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

        // 获取或创建文本子元素（与think块分离）
        let textElement = afterContentElement.querySelector('.tool-after-text');
        if (!textElement) {
            textElement = document.createElement('div');
            textElement.className = 'tool-after-text';
            textElement._textBuffer = '';
            afterContentElement.appendChild(textElement);
        }

        // 初始化缓冲区
        if (textElement._textBuffer === undefined) {
            textElement._textBuffer = '';
        }

        // 将新内容与标签缓冲区合并
        const fullContent = this.tagBuffer + content;

        console.log('💭 [工具后内容] 标签缓冲区:', JSON.stringify(this.tagBuffer), '新内容:', JSON.stringify(content), '合并后:', JSON.stringify(fullContent));

        // 处理思考内容 - 传入afterContentElement用于放置think块
        const result = this.processThinkContent(fullContent, afterContentElement);

        console.log('💭 [工具后内容] 处理结果 - 普通内容:', JSON.stringify(result.processedContent), '新缓冲区:', JSON.stringify(result.tagBuffer));

        // 更新标签缓冲区
        this.tagBuffer = result.tagBuffer;

        // 累积内容并渲染Markdown到textElement
        if (result.processedContent) {
            textElement._textBuffer += result.processedContent;
            textElement.innerHTML = this.renderMarkdown(textElement._textBuffer);
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
    addFileOperationButton({ filepath, operationMode, toolCallElement, parallelCallId }) {
        const fileName = filepath.split('/').pop();
        const fileIcon = this.getFileIcon(fileName);

        // 找到对应的计划子步骤
        let stepEl = this._findPlanStepForParallelTask(parallelCallId);
        if (!stepEl) {
            stepEl = this._findInProgressStep();
        }
        // 终极 fallback：找第一个 not_started 的步骤
        if (!stepEl) {
            stepEl = this._findFirstNotStartedStep();
        }

        // 去重：同一个步骤下同一个文件路径只显示一个条目
        if (stepEl) {
            let filesContainer = stepEl.querySelector('.step-files');
            if (filesContainer) {
                const existing = filesContainer.querySelector(`.plan-file-item[data-filepath="${CSS.escape(filepath)}"]`);
                if (existing) {
                    // 已存在，复用引用即可
                    if (toolCallElement) {
                        toolCallElement._planFileItem = existing;
                        toolCallElement._planDownloadBtn = existing.querySelector('.plan-file-download');
                        toolCallElement._planFileStatus = existing.querySelector('.plan-file-status');
                    }
                    return existing;
                }
            }
        }

        // 构建文件条目 DOM
        const fileItem = document.createElement('div');
        fileItem.className = 'plan-file-item';
        fileItem.dataset.filepath = filepath;

        const statusSpan = document.createElement('span');
        statusSpan.className = 'plan-file-status';
        statusSpan.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'plan-file-download';
        downloadBtn.innerHTML = '<i class="fas fa-download"></i> 下载';
        downloadBtn.onclick = (e) => {
            e.stopPropagation();
            this.downloadPlanFile(filepath, fileName);
        };

        fileItem.innerHTML = `
            <i class="${fileIcon} plan-file-icon"></i>
            <div class="plan-file-info">
                <div class="plan-file-name" title="${this.escapeHtml(filepath)}">${this.escapeHtml(fileName)}</div>
            </div>
        `;
        fileItem.appendChild(statusSpan);
        fileItem.appendChild(downloadBtn);

        // 点击文件项 → 打开预览弹窗（可实时查看流式写入）
        fileItem.onclick = (e) => {
            if (e.target.closest('.plan-file-download')) return;
            this.openFilePreview(filepath, fileName);
        };

        // 挂载到对应计划步骤
        if (stepEl) {
            let filesContainer = stepEl.querySelector('.step-files');
            if (!filesContainer) {
                filesContainer = document.createElement('div');
                filesContainer.className = 'step-files';
                stepEl.appendChild(filesContainer);
            }
            filesContainer.appendChild(fileItem);
        }

        // 保存引用到 toolCallElement 以便完成时更新
        if (toolCallElement) {
            toolCallElement._planFileItem = fileItem;
            toolCallElement._planDownloadBtn = downloadBtn;
            toolCallElement._planFileStatus = statusSpan;
        }

        // 打开侧边栏
        if (this.elements.sidebar) {
            this.elements.sidebar.classList.add('open');
        }

        // 初始化该文件的内容缓冲
        if (!this._planFileContents) this._planFileContents = {};
        if (!this._planFileContents[filepath]) {
            this._planFileContents[filepath] = '';
        }

        return fileItem;
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
        this.elements.fileContent.innerHTML = '';
        this._fileContentBuffer = '';

        // 保存当前文件路径，用于流式更新
        this.currentFilePath = filePath;
        this.currentFileMode = operationMode;

        try {
            // 方案1：先尝试从DOM中读取已接收的内容
            const cachedContent = this.getFileContentFromToolResult(filePath);

            if (cachedContent) {
                // 如果找到了缓存内容，渲染为Markdown
                const textContent = this.extractTextFromHTML(cachedContent);
                this.elements.fileContent.innerHTML = this.renderMarkdown(textContent);

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
                // 渲染Markdown内容
                this.elements.fileContent.innerHTML = this.renderMarkdown(data.content);

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
     * 获取指定并行任务当前活跃的文件路径
     * 返回最后一个（最新的）活跃文件操作
     */
    _getCurrentFilePathForParallelTask(parallelCallId) {
        const files = this._parallelActiveFiles?.[parallelCallId];
        if (!files || files.length === 0) return null;
        // 返回最后一个（最新的）文件
        return files[files.length - 1]?.filepath || null;
    }

    /**
     * 更新文件内容流
     */
    // 过滤文件内容中的 agent 进度标记行
    _filterFileContent(text) {
        return text
            .replace(/^[\s\-]*(?:当前开始搜索[：:]|已完成[搜索]*[：:]|---\s*已完成[搜索]*[：:]|正在搜索[：:]|开始搜索[：:]|搜索完成[：:]|开始分析[：:]|分析完成[：:]|当前开始分析[：:]).*$/gm, '')
            .replace(/\n{3,}/g, '\n\n')
            .replace(/^\n+/, '');
    }

    updateFileContentStream(filePath, content) {
        if (!content) return;

        // 原样累积到缓冲区
        if (!this._planFileContents) this._planFileContents = {};
        this._planFileContents[filePath] = (this._planFileContents[filePath] || '') + content;

        // 渲染时统一过滤完整文本（避免跨 chunk 的进度行匹配不到）
        if (this._previewFilePath === filePath) {
            const contentEl = document.getElementById('filePreviewContent');
            const downloadBtn = document.getElementById('filePreviewDownloadBtn');
            if (contentEl) {
                const filtered = this._filterFileContent(this._planFileContents[filePath]);
                contentEl.innerHTML = this.renderMarkdown(filtered);
                // 仅当用户未手动滚动时才自动跟随到底部（实时查看最新内容）
                if (!contentEl._userScrolled) {
                    contentEl.scrollTop = contentEl.scrollHeight;
                }
            }
            if (downloadBtn) downloadBtn.style.display = 'inline-flex';
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
        // 忽略程序触发的滚动
        if (this._programmaticScrollCount > 0) {
            return;
        }

        const element = e.target;
        const scrollTop = element.scrollTop;
        const scrollHeight = element.scrollHeight;
        const clientHeight = element.clientHeight;
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

        if (distanceFromBottom > this.scrollThreshold) {
            this.userScrolledUp = true;
            this.showScrollToBottomButton();
        } else {
            this.userScrolledUp = false;
            this.hideScrollToBottomButton();
        }

        this.lastScrollTop = scrollTop;
    }

    /**
     * 智能滚动到底部 - 只在用户位于底部时才自动滚动（去抖）
     */
    scrollToBottom() {
        if (this.userScrolledUp) {
            return;
        }

        // 去抖：多次快速调用只执行最后一次
        if (this._scrollRAF) {
            cancelAnimationFrame(this._scrollRAF);
        }
        this._scrollRAF = requestAnimationFrame(() => {
            this._scrollRAF = null;
            if (this.userScrolledUp) return;
            if (!this._programmaticScrollCount) this._programmaticScrollCount = 0;
            this._programmaticScrollCount++;
            this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
            // 延迟两帧再恢复，确保 scroll 事件完全被忽略
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    this._programmaticScrollCount = Math.max(0, this._programmaticScrollCount - 1);
                });
            });
        });
    }

    /**
     * 强制滚动到底部 - 无论用户位置如何都滚动
     */
    forceScrollToBottom() {
        this.userScrolledUp = false;
        this.hideScrollToBottomButton();
        if (this._scrollRAF) {
            cancelAnimationFrame(this._scrollRAF);
            this._scrollRAF = null;
        }
        if (!this._programmaticScrollCount) this._programmaticScrollCount = 0;
        this._programmaticScrollCount++;
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                this._programmaticScrollCount = Math.max(0, this._programmaticScrollCount - 1);
            });
        });
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
     * 隔离版 processThinkContent - 每个并行子任务使用独立的 think 状态
     * 避免多个并行流共享 this.isInThinkBlock 等全局状态导致内容错位
     */
    _processThinkContentIsolated(content, parentElement, thinkState) {
        let processedContent = '';
        let remainingContent = content;
        let newTagBuffer = '';

        while (remainingContent.length > 0) {
            if (thinkState.isInThinkBlock) {
                const endThinkIndex = remainingContent.indexOf('</think>');
                const endThinkingIndex = remainingContent.indexOf('</thinking>');

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
                    const finalContent = remainingContent.substring(0, endIndex);
                    if (finalContent && thinkState.currentThinkElement) {
                        thinkState.currentThinkElement.appendChild(document.createTextNode(finalContent));
                    }
                    // 结束 think 块
                    thinkState.isInThinkBlock = false;
                    thinkState.currentThinkBlock = null;
                    thinkState.currentThinkElement = null;

                    remainingContent = remainingContent.substring(endIndex + endTagLength);
                    continue;
                } else {
                    if (this.mightHavePartialEndTag(remainingContent)) {
                        newTagBuffer = remainingContent;
                        break;
                    }
                    if (thinkState.currentThinkElement) {
                        thinkState.currentThinkElement.appendChild(document.createTextNode(remainingContent));
                    }
                    break;
                }
            } else {
                const startThinkIndex = remainingContent.indexOf('<think>');
                const startThinkingIndex = remainingContent.indexOf('<thinking>');

                let startIndex = -1;
                let startTagLength = 0;

                if (startThinkIndex !== -1 && (startThinkingIndex === -1 || startThinkIndex < startThinkingIndex)) {
                    startIndex = startThinkIndex;
                    startTagLength = '<think>'.length;
                } else if (startThinkingIndex !== -1) {
                    startIndex = startThinkingIndex;
                    startTagLength = '<thinking>'.length;
                }

                if (startIndex !== -1) {
                    const beforeThink = remainingContent.substring(0, startIndex);
                    processedContent += beforeThink;

                    // 创建新的 think 块（隔离版，不修改全局 this 状态）
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
                    parentElement.appendChild(thinkBlock);

                    thinkState.isInThinkBlock = true;
                    thinkState.currentThinkBlock = thinkBlock;
                    thinkState.currentThinkElement = thinkBlock.querySelector(`#text_${thinkId}`);

                    remainingContent = remainingContent.substring(startIndex + startTagLength);
                    continue;
                } else {
                    if (this.mightHavePartialStartTag(remainingContent)) {
                        const partialTagIndex = this.findPartialTagStart(remainingContent);
                        processedContent += remainingContent.substring(0, partialTagIndex);
                        newTagBuffer = remainingContent.substring(partialTagIndex);
                        break;
                    }
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
        const patterns = ['<', '<t', '<th', '<thi', '<thin', '<think', '<thinki', '<thinkin', '<thinking'];
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
        const patterns = ['</', '</t', '</th', '</thi', '</thin', '</think', '</thinki', '</thinkin', '</thinking'];
        
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
    toggleSidebar() {
        if (this.elements.sidebar.classList.contains('open')) {
            this.elements.sidebar.classList.remove('open');
        } else {
            this.elements.sidebar.classList.add('open');
        }
    }

    /**
     * 显示文件列表视图 (legacy)
     */
    showFileListView() {}

    /**
     * 显示文件内容视图 (legacy)
     */
    showFileContentView(fileName) {}

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
        this.elements.fileContent.innerHTML = '<p style="color:#64748b;">加载中...</p>';

        try {
            const response = await fetch(`${this.apiBaseUrl}/file/read?filepath=${encodeURIComponent(filePath)}`);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.status === 'success' && data.content) {
                this.elements.fileContent.innerHTML = this.renderMarkdown(data.content);
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
     * 下载文件
     */
    downloadFile() {
        // legacy, unused
    }

    /**
     * 从计划面板下载生成的文件
     */
    downloadPlanFile(filepath, fileName) {
        const raw = this._planFileContents?.[filepath];
        if (!raw) {
            alert('文件内容尚未就绪');
            return;
        }
        const content = this._filterFileContent(raw);

        try {
            const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            console.log('📥 文件下载成功:', fileName);
        } catch (error) {
            console.error('📥 文件下载失败:', error);
            alert('下载失败: ' + error.message);
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
     * 显示侧边栏指定视图（文件/计划）
     */
    showSidebarView(viewType) {
        // 侧边栏现在只有计划视图，直接打开
        if (this.elements.sidebar) {
            this.elements.sidebar.classList.add('open');
        }
    }

    /**
     * 从 Markdown 字符串解析计划
     * 格式：# 标题\n## 组名\n- [√] 步骤描述\n...
     */
    parsePlanFromMarkdown(markdown) {
        const lines = markdown.split('\n');
        const plan = {
            title: '未加载计划',
            groups: [],
            totalSteps: 0,
            completedSteps: 0
        };

        let currentGroup = null;
        let stepIndex = 0;

        for (const line of lines) {
            // 提取标题
            if (line.startsWith('# ')) {
                plan.title = line.substring(2).trim();
            }
            // 提取组名
            else if (line.startsWith('## ')) {
                if (currentGroup) {
                    plan.groups.push(currentGroup);
                }
                currentGroup = {
                    name: line.substring(3).trim(),
                    steps: []
                };
            }
            // 提取步骤（如 "- [√] 描述"）
            else if (line.startsWith('- ') && currentGroup) {
                const match = line.match(/^- \[([\[\]√!x ]*)\] (.*)/);
                if (match) {
                    const statusSymbol = match[1];
                    let stepText = match[2].trim();
                    let stepType = '';

                    // 提取【AGENT_TYPE】标签
                    const typeMatch = stepText.match(/^【([^】]+)】\s*(.*)/);
                    if (typeMatch) {
                        stepType = typeMatch[1];
                        stepText = typeMatch[2];
                    }

                    let status = 'not_started';
                    if (statusSymbol === '√') status = 'completed';
                    else if (statusSymbol === 'x') status = 'in_progress';
                    else if (statusSymbol === '!') status = 'blocked';

                    currentGroup.steps.push({
                        index: stepIndex,
                        text: stepText,
                        type: stepType,
                        status: status,
                        symbol: `[${statusSymbol}]`
                    });

                    plan.totalSteps++;
                    if (status === 'completed') plan.completedSteps++;
                    stepIndex++;
                }
            }
        }

        if (currentGroup) {
            plan.groups.push(currentGroup);
        }

        return plan;
    }

    /**
     * 渲染计划面板
     */
    renderPlanPanel() {
        if (!this.activePlan) return;

        const planTitle = document.getElementById('planTitle');
        const planProgress = document.getElementById('planProgress');
        const planStepsContainer = document.getElementById('planSteps');

        if (!planTitle || !planProgress || !planStepsContainer) {
            console.warn('计划面板 DOM 元素不完整');
            return;
        }

        // 在清空前，保存每个步骤下已挂载的文件元素
        const savedFiles = {}; // stepIndex → [fileItem DOM elements]
        if (this.planStepElements) {
            for (const [stepIndex, stepEl] of Object.entries(this.planStepElements)) {
                const filesContainer = stepEl.querySelector('.step-files');
                if (filesContainer && filesContainer.children.length > 0) {
                    savedFiles[stepIndex] = Array.from(filesContainer.children);
                }
            }
        }

        planTitle.textContent = this.activePlan.title;
        planProgress.textContent = `${this.activePlan.completedSteps}/${this.activePlan.totalSteps} 完成`;

        planStepsContainer.innerHTML = '';
        this.planStepElements = {};

        for (const group of this.activePlan.groups) {
            const groupDiv = document.createElement('div');
            groupDiv.className = 'plan-group';

            const groupHeader = document.createElement('div');
            groupHeader.className = 'plan-group-header';

            const chevron = document.createElement('i');
            chevron.className = 'fas fa-chevron-right plan-group-chevron';

            const groupTitle = document.createElement('h4');
            groupTitle.textContent = group.name;

            // 计算组内完成进度
            const groupCompleted = group.steps.filter(s => s.status === 'completed').length;
            const groupTotal = group.steps.length;
            const groupProgress = document.createElement('span');
            groupProgress.className = 'plan-group-progress';
            groupProgress.textContent = `${groupCompleted}/${groupTotal}`;

            groupHeader.appendChild(chevron);
            groupHeader.appendChild(groupTitle);
            groupHeader.appendChild(groupProgress);
            groupDiv.appendChild(groupHeader);

            const stepsList = document.createElement('div');
            stepsList.className = 'plan-steps-list';
            stepsList.style.display = 'none';

            groupHeader.onclick = () => {
                const isHidden = stepsList.style.display === 'none';
                stepsList.style.display = isHidden ? '' : 'none';
                chevron.classList.toggle('expanded', isHidden);
            };

            for (const step of group.steps) {
                const stepDiv = document.createElement('div');
                stepDiv.className = `plan-step ${step.status}`;
                stepDiv.dataset.stepIndex = step.index;

                const statusSpan = document.createElement('span');
                statusSpan.className = `step-status ${step.status}`;
                statusSpan.innerHTML = this._stepStatusIcon(step.status);

                const textSpan = document.createElement('span');
                textSpan.className = `step-text ${step.status}`;
                textSpan.textContent = step.text;

                stepDiv.appendChild(statusSpan);
                if (step.type) {
                    const typeBadge = document.createElement('span');
                    typeBadge.className = 'step-type-badge';
                    typeBadge.textContent = step.type;
                    stepDiv.appendChild(typeBadge);
                }
                stepDiv.appendChild(textSpan);

                // 恢复该步骤之前挂载的文件元素
                if (savedFiles[step.index]) {
                    const filesContainer = document.createElement('div');
                    filesContainer.className = 'step-files';
                    savedFiles[step.index].forEach(fileEl => filesContainer.appendChild(fileEl));
                    stepDiv.appendChild(filesContainer);
                }

                stepsList.appendChild(stepDiv);

                this.planStepElements[step.index] = stepDiv;
            }

            groupDiv.appendChild(stepsList);
            planStepsContainer.appendChild(groupDiv);
        }

        console.log('📋 计划面板已渲染:', this.activePlan);
    }

    /**
     * 更新计划面板（只更新已变化的步骤）
     */
    updatePlanPanel() {
        if (!this.activePlan) return;

        const planProgress = document.getElementById('planProgress');
        if (planProgress) {
            planProgress.textContent = `${this.activePlan.completedSteps}/${this.activePlan.totalSteps} 完成`;
        }

        // 更新所有步骤的视觉状态
        for (const [stepIndex, stepEl] of Object.entries(this.planStepElements)) {
            const step = this._findStepByIndex(parseInt(stepIndex));
            if (step) {
                stepEl.className = `plan-step ${step.status}`;

                const statusSpan = stepEl.querySelector('.step-status');
                if (statusSpan) {
                    statusSpan.className = `step-status ${step.status}`;
                    statusSpan.innerHTML = this._stepStatusIcon(step.status);
                }

                const textSpan = stepEl.querySelector('.step-text');
                if (textSpan) {
                    textSpan.className = `step-text ${step.status}`;
                }
            }
        }

        // 更新每个组的进度计数
        const planStepsContainer = document.getElementById('planSteps');
        if (planStepsContainer) {
            this.activePlan.groups.forEach((group, idx) => {
                const groupDiv = planStepsContainer.children[idx];
                if (groupDiv) {
                    const progressEl = groupDiv.querySelector('.plan-group-progress');
                    if (progressEl) {
                        const done = group.steps.filter(s => s.status === 'completed').length;
                        progressEl.textContent = `${done}/${group.steps.length}`;
                    }
                }
            });
        }

        console.log('📋 计划面板已更新');
    }

    /**
     * 根据步骤索引查找步骤对象
     */
    _findStepByIndex(index) {
        for (const group of this.activePlan.groups) {
            for (const step of group.steps) {
                if (step.index === index) return step;
            }
        }
        return null;
    }

    _stepStatusIcon(status) {
        switch (status) {
            case 'completed': return '<i class="fas fa-check-circle"></i>';
            case 'in_progress': return '<i class="fas fa-spinner"></i>';
            case 'blocked': return '<i class="fas fa-exclamation-circle"></i>';
            default: return '<i class="far fa-circle"></i>';
        }
    }

    /**
     * 通过 agentName/taskDesc 模糊匹配计划步骤，并标记为 in_progress
     */
    _markStepInProgressByMatch(agentName, taskDesc) {
        if (!this.activePlan) return;
        let bestMatch = null;
        let bestScore = 0;
        for (const group of this.activePlan.groups) {
            for (const step of group.steps) {
                if (step.status === 'completed' || step.status === 'in_progress') continue;
                let score = 0;
                if (agentName && step.type && agentName.toUpperCase().includes(step.type.toUpperCase())) {
                    score += 10;
                }
                if (taskDesc && step.text) {
                    const keywords = taskDesc.split(/[\s，、,。]+/).filter(k => k.length > 1);
                    const matched = keywords.filter(k => step.text.includes(k));
                    if (matched.length > 0) score += matched.join('').length;
                }
                if (score > bestScore) {
                    bestScore = score;
                    bestMatch = step;
                }
            }
        }
        if (bestMatch) {
            bestMatch.status = 'in_progress';
            const stepEl = this.planStepElements?.[bestMatch.index];
            if (stepEl) {
                stepEl.className = `plan-step in_progress`;
                const statusSpan = stepEl.querySelector('.step-status');
                if (statusSpan) {
                    statusSpan.className = 'step-status in_progress';
                    statusSpan.innerHTML = this._stepStatusIcon('in_progress');
                }
            }
        }
    }

    /**
     * 根据 parallelCallId 找到对应的计划步骤 DOM 元素
     * 通过任务描述与计划步骤文本模糊匹配
     */
    _findPlanStepForParallelTask(parallelCallId) {
        if (!parallelCallId || !this.activePlan) return null;

        // 优先使用预计算的映射
        const precomputedIndex = this._parallelCallIdToStepIndex?.[parallelCallId];
        if (precomputedIndex !== undefined && this.planStepElements[precomputedIndex]) {
            return this.planStepElements[precomputedIndex];
        }

        // 回退：通过任务描述文本匹配
        const taskDesc = this._parallelTaskDescMap?.[parallelCallId];
        if (!taskDesc) return null;

        let bestMatch = null;
        let bestScore = 0;

        for (const group of this.activePlan.groups) {
            for (const step of group.steps) {
                let score = 0;
                if (taskDesc.includes(step.text) || step.text.includes(taskDesc)) {
                    score = Math.min(taskDesc.length, step.text.length) * 2;
                } else {
                    // 模糊匹配：关键词重叠
                    const keywords = taskDesc.split(/[\s，、,。]+/).filter(k => k.length > 1);
                    const matched = keywords.filter(k => step.text.includes(k));
                    if (matched.length > 0) {
                        score = matched.join('').length;
                    }
                }
                if (score > bestScore) {
                    bestScore = score;
                    bestMatch = step;
                }
            }
        }

        if (bestMatch && this.planStepElements[bestMatch.index]) {
            return this.planStepElements[bestMatch.index];
        }
        return null;
    }

    /**
     * 找到当前 in_progress 的步骤（兜底：文件挂到正在执行的步骤）
     */
    _findInProgressStep() {
        if (!this.activePlan) return null;
        for (const group of this.activePlan.groups) {
            for (const step of group.steps) {
                if (step.status === 'in_progress' && this.planStepElements[step.index]) {
                    return this.planStepElements[step.index];
                }
            }
        }
        return null;
    }

    _findFirstNotStartedStep() {
        if (!this.activePlan) return null;
        for (const group of this.activePlan.groups) {
            for (const step of group.steps) {
                if (step.status === 'not_started' && this.planStepElements[step.index]) {
                    return this.planStepElements[step.index];
                }
            }
        }
        return null;
    }

    /**
     * 打开文件预览弹窗（支持查看流式写入内容）
     */
    openFilePreview(filepath, fileName) {
        this._previewFilePath = filepath;
        this._previewFileName = fileName;

        const overlay = document.getElementById('filePreviewOverlay');
        const title = document.getElementById('filePreviewTitle');
        const content = document.getElementById('filePreviewContent');
        const downloadBtn = document.getElementById('filePreviewDownloadBtn');

        if (!overlay) return;

        title.textContent = fileName;
        overlay.style.display = 'flex';

        // 重置滚动状态：打开时默认自动跟随，用户手动滚动后停止
        content._userScrolled = false;
        if (!content._scrollListenerBound) {
            content.addEventListener('scroll', () => {
                const distFromBottom = content.scrollHeight - content.scrollTop - content.clientHeight;
                // 改进检测逻辑：如果距离底部超过150px，则认为用户在浏览历史内容
                // 如果距离底部很近（小于30px），则认为用户在看最新内容
                if (distFromBottom > 150) {
                    content._userScrolled = true;
                } else if (distFromBottom <= 30) {
                    content._userScrolled = false;
                }
                // 30-150px之间保持现状，避免频繁切换
            });
            content._scrollListenerBound = true;
        }

        const fileContent = this._planFileContents?.[filepath] || '';
        if (fileContent) {
            content.innerHTML = this.renderMarkdown(this._filterFileContent(fileContent));
            downloadBtn.style.display = 'inline-flex';
            // 打开预览时总是滚动到顶部，让用户看到完整内容的开头
            content.scrollTop = 0;
            content._userScrolled = false;
        } else {
            content.innerHTML = '<div class="file-preview-hint"><i class="fas fa-spinner fa-spin"></i> 正在写入...</div>';
            downloadBtn.style.display = 'none';
        }
    }

    /**
     * 关闭文件预览弹窗
     */
    closeFilePreview() {
        const overlay = document.getElementById('filePreviewOverlay');
        if (overlay) overlay.style.display = 'none';
        this._previewFilePath = null;
        this._previewFileName = null;
    }

    /**
     * 从预览弹窗下载文件
     */
    downloadPreviewFile() {
        if (this._previewFilePath && this._previewFileName) {
            this.downloadPlanFile(this._previewFilePath, this._previewFileName);
        }
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

        // 重置并行任务状态
        this._currentParallelGroup = null;
        this._parallelCallIds = null;
        this._parallelCompleted = 0;
        this._parallelTotal = 0;

        // 重置计划相关状态
        this.activePlan = null;
        this.planStepElements = {};
        this._planFileContents = {};

        // 重置计划面板
        const planTitle = document.getElementById('planTitle');
        const planProgress = document.getElementById('planProgress');
        const planSteps = document.getElementById('planSteps');
        if (planTitle) planTitle.textContent = '未加载计划';
        if (planProgress) planProgress.textContent = '0/0 完成';
        if (planSteps) planSteps.innerHTML = '';
        this.closeFilePreview();

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

// 全局并行任务折叠/展开函数
function toggleParallelTask(callId) {
    const body = document.getElementById(`pbody_${callId}`);
    const toggle = document.getElementById(`ptoggle_${callId}`);
    if (body) {
        const isHidden = body.style.display === 'none';
        body.style.display = isHidden ? 'block' : 'none';
        if (toggle) {
            toggle.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
        }
    }
}
window.toggleParallelTask = toggleParallelTask;

// ============= 计划相关全局函数 =============

/**
 * 显示侧边栏指定视图
 */
window.showSidebarView = function(viewType) {
    if (!window.app) return;
    app.showSidebarView(viewType);
};

/**
 * 调试函数：手动触发消息发送
 */
window.testSendMessage = function() {
    console.log('🧪 测试发送消息');
    if (!window.app) {
        console.error('❌ app 未初始化');
        return;
    }
    console.log('✅ app 已初始化');
    console.log('elements:', window.app.elements);
    window.app.sendMessage();
};

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', () => {
    console.log('AI助手应用已启动');
});