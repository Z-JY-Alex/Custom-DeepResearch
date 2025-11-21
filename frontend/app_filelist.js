// 文件列表相关功能扩展
// 在app.js的AIAssistantApp类中添加以下方法

/**
 * 在构造函数中初始化文件列表相关变量
 * 添加到 constructor() 中：
 */
// this.knownFiles = new Set(); // 已知文件路径集合
// this.fileListAutoRefresh = null; // 自动刷新定时器
// this.isFileListOpen = false; // 文件列表是否打开

/**
 * 打开文件列表侧边栏
 */
openFileList() {
    console.log('📂 尝试打开文件列表');
    console.log('📂 当前 session_id:', this.currentSessionId);

    // 如果没有 session_id，尝试智能检测
    if (!this.currentSessionId) {
        console.log('📂 session_id 为空，尝试智能检测...');

        // 方法1：从 localStorage 恢复
        const savedSessionId = localStorage.getItem('lastSessionId');
        if (savedSessionId) {
            console.log('📂 从 localStorage 恢复 session_id:', savedSessionId);
            this.currentSessionId = savedSessionId;
        }

        // 方法2：从页面上的文件操作按钮中提取
        if (!this.currentSessionId) {
            const fileButtons = document.querySelectorAll('.file-operation');
            if (fileButtons.length > 0) {
                for (const btn of fileButtons) {
                    const filepath = btn.closest('.tool-call')?.dataset?.filepath;
                    if (filepath) {
                        // 文件路径格式通常是: {session_id}/filename
                        const match = filepath.match(/^([^\/]+)\//);
                        if (match) {
                            this.currentSessionId = match[1];
                            console.log('📂 从文件路径中提取 session_id:', this.currentSessionId);
                            // 保存到 localStorage
                            localStorage.setItem('lastSessionId', this.currentSessionId);
                            break;
                        }
                    }
                }
            }
        }

        // 方法3：提示用户手动输入
        if (!this.currentSessionId) {
            // 尝试从工具调用元素中提取
            const toolCalls = document.querySelectorAll('.tool-call[data-filepath]');
            console.log('📂 找到的工具调用元素数量:', toolCalls.length);

            if (toolCalls.length > 0) {
                const firstPath = toolCalls[0].dataset.filepath;
                console.log('📂 第一个文件路径:', firstPath);
                if (firstPath) {
                    const match = firstPath.match(/^([^\/]+)\//);
                    if (match) {
                        this.currentSessionId = match[1];
                        console.log('📂 从工具调用中提取 session_id:', this.currentSessionId);
                        localStorage.setItem('lastSessionId', this.currentSessionId);
                    }
                }
            }
        }

        // 如果还是没有，让用户输入
        if (!this.currentSessionId) {
            const userInput = prompt('请输入 session ID（可在文件路径中找到，格式如：8dc0617b-db73-48d9-bd22-0887fd2eacde）：');
            if (userInput && userInput.trim()) {
                this.currentSessionId = userInput.trim();
                localStorage.setItem('lastSessionId', this.currentSessionId);
                console.log('📂 用户输入的 session_id:', this.currentSessionId);
            } else {
                alert('无法获取 session ID，请先发送消息创建会话');
                return;
            }
        }
    }

    console.log('📂 最终使用的 session_id:', this.currentSessionId);

    // 标记文件列表已打开
    this.isFileListOpen = true;

    // 打开侧边栏
    this.elements.sidebar.classList.add('open');

    // 显示文件列表视图
    showFileList();

    // 加载文件列表
    this.loadFileList();

    // 启动自动刷新（每5秒刷新一次）
    this.startFileListAutoRefresh();
}

/**
 * 启动文件列表自动刷新
 */
startFileListAutoRefresh() {
    // 清除旧的定时器
    if (this.fileListAutoRefresh) {
        clearInterval(this.fileListAutoRefresh);
    }

    // 每5秒自动刷新一次
    this.fileListAutoRefresh = setInterval(() => {
        // 只在文件列表视图且侧边栏打开时刷新
        if (this.isFileListOpen &&
            this.elements.sidebar.classList.contains('open') &&
            document.getElementById('fileListView').style.display !== 'none') {
            console.log('🔄 自动刷新文件列表');
            this.loadFileList(true); // 静默刷新，不显示加载状态
        }
    }, 5000);
}

/**
 * 停止文件列表自动刷新
 */
stopFileListAutoRefresh() {
    if (this.fileListAutoRefresh) {
        clearInterval(this.fileListAutoRefresh);
        this.fileListAutoRefresh = null;
    }
}

/**
 * 当文件操作完成时刷新文件列表
 * 在 handleToolResultEnd 中调用此方法
 */
onFileOperationComplete(toolName) {
    if (toolName === 'stream_file_operation' && this.isFileListOpen) {
        console.log('📂 检测到文件操作完成，刷新文件列表');
        // 延迟500ms刷新，确保文件已写入完成
        setTimeout(() => {
            if (this.elements.sidebar.classList.contains('open') &&
                document.getElementById('fileListView').style.display !== 'none') {
                this.loadFileList(true);
            }
        }, 500);
    }
}

/**
 * 加载文件列表
 * @param {boolean} silent - 是否静默刷新（不显示加载状态）
 */
async loadFileList(silent = false) {
    const fileListEl = document.getElementById('fileList');
    const fileCountEl = document.getElementById('fileCount');

    try {
        if (!silent) {
            // 显示加载状态
            fileCountEl.textContent = '加载中...';
            fileListEl.innerHTML = `
                <div style="text-align: center; padding: 40px; color: #64748b;">
                    <i class="fas fa-spinner fa-spin" style="font-size: 32px; margin-bottom: 12px;"></i>
                    <div>正在加载文件列表...</div>
                </div>
            `;
        }

        console.log('📂 开始加载文件列表，session_id:', this.currentSessionId);

        const response = await fetch(`${this.apiBaseUrl}/file/list?session_id=${encodeURIComponent(this.currentSessionId)}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        console.log('📂 文件列表加载成功:', data);

        // 检测新文件
        const newFiles = [];
        if (this.knownFiles && this.knownFiles.size > 0) {
            data.files.forEach(file => {
                if (!this.knownFiles.has(file.path)) {
                    newFiles.push(file.path);
                }
            });
        }

        // 更新已知文件集合
        if (!this.knownFiles) {
            this.knownFiles = new Set();
        }
        this.knownFiles.clear();
        data.files.forEach(file => this.knownFiles.add(file.path));

        // 更新文件数量
        fileCountEl.textContent = `共 ${data.count} 个文件`;
        if (newFiles.length > 0) {
            fileCountEl.textContent += ` (${newFiles.length} 个新文件)`;
        }

        // 渲染文件列表
        if (data.files && data.files.length > 0) {
            fileListEl.innerHTML = data.files.map(file => {
                const icon = this.getFileIcon(file.name);
                const size = this.formatFileSize(file.size);
                const time = this.formatTime(file.modified);
                const isNew = newFiles.includes(file.path);

                return `
                    <div class="file-item ${isNew ? 'file-item-new' : ''}" onclick="app.showFileFromList('${this.escapeHtml(file.path)}', '${this.escapeHtml(file.name)}', ${file.size}, '${file.modified}')">
                        <div class="file-item-header">
                            <i class="${icon} file-item-icon"></i>
                            <div class="file-item-name">${this.escapeHtml(file.name)}</div>
                            ${isNew ? '<span class="new-badge">新</span>' : ''}
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

            // 如果有新文件，滚动到顶部以显示它们
            if (newFiles.length > 0 && !silent) {
                fileListEl.scrollTop = 0;
            }
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
        if (!silent) {
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
}

/**
 * 从文件列表中显示文件
 */
async showFileFromList(filePath, fileName, fileSize, modified) {
    console.log('📄 显示文件:', filePath);

    // 停止自动刷新（查看文件内容时不需要刷新列表）
    this.stopFileListAutoRefresh();

    // 切换到文件内容视图
    document.getElementById('fileListView').style.display = 'none';
    document.getElementById('fileContentView').style.display = 'block';
    document.getElementById('backButton').style.display = 'flex';
    document.getElementById('sidebarTitle').textContent = fileName;

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

// 全局函数：返回文件列表
function showFileList() {
    document.getElementById('fileListView').style.display = 'block';
    document.getElementById('fileContentView').style.display = 'none';
    document.getElementById('backButton').style.display = 'none';
    document.getElementById('sidebarTitle').textContent = '文件列表';

    // 返回文件列表时，重新启动自动刷新
    if (window.app && window.app.isFileListOpen) {
        window.app.startFileListAutoRefresh();
    }
}

// 重写 closeSidebar 函数，停止自动刷新
function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');

    // 停止自动刷新
    if (window.app) {
        window.app.isFileListOpen = false;
        window.app.stopFileListAutoRefresh();
    }
}

