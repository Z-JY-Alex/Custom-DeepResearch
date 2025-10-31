# Agent流式API前端示例

这个文件夹包含了用于连接和使用Agent流式API的前端示例代码和组件。

## 文件说明

### 1. `frontend_example.html`
完整的HTML页面示例，包含：
- 🎨 现代化的UI界面
- 📡 实时流式数据接收
- 🔧 工具调用监控
- 📁 文件操作跟踪
- 📊 Token使用情况显示
- 🎯 事件类型识别和分类显示

**使用方法：**
```bash
# 启动后端API服务
cd backend
python api/stream_api.py

# 在浏览器中打开HTML文件
# 或者使用简单的HTTP服务器
python -m http.server 8080
# 然后访问 http://localhost:8080/frontend_example.html
```

### 2. `agent_stream_client.js`
JavaScript客户端库，提供：
- 🔌 AgentStreamClient 类：核心流式客户端
- 🎯 AgentEventHandler 类：事件处理器基类
- 🏭 AgentStreamClientFactory：便捷的工厂函数
- 📱 支持浏览器和Node.js环境

**基础使用：**
```javascript
// 创建客户端
const client = new AgentStreamClient({
    baseUrl: 'http://localhost:8000',
    onEvent: (event) => {
        console.log('收到事件:', event.event_type, event.content);
    }
});

// 执行Agent任务
await client.execute({
    query: '制定一个计划，计算1+1的结果',
    agent_type: 'PlanAgent',
    max_rounds: 50
});
```

**高级使用（事件处理器）：**
```javascript
class MyEventHandler extends AgentEventHandler {
    onAgentContent(event) {
        document.getElementById('output').textContent += event.content;
    }
    
    onToolResultContent(event) {
        if (event.is_streaming_file) {
            document.getElementById('fileContent').textContent += event.content;
        }
    }
}

const handler = new MyEventHandler();
const client = AgentStreamClientFactory.createClientWithHandler(handler);
```

### 3. `AgentStreamComponent.jsx`
React组件，提供：
- ⚛️ 完整的React Hook集成
- 🎛️ 可配置的UI组件
- 📊 实时状态监控
- 🔄 自动滚动和事件管理
- 📱 响应式设计

**使用方法：**
```jsx
import AgentStreamComponent from './AgentStreamComponent';

function App() {
    return (
        <AgentStreamComponent
            baseUrl="http://localhost:8000"
            defaultQuery="制定一个计划，计算1+1的结果"
            onExecutionComplete={(data) => {
                console.log('执行完成:', data);
            }}
        />
    );
}
```

## 事件类型说明

API返回的流式事件包含以下类型：

| 事件类型 | 说明 | 关键字段 |
|---------|------|----------|
| `agent_start` | Agent开始执行 | `agent_name`, `query` |
| `agent_content` | Agent普通内容输出 | `content` |
| `tool_call_start` | 工具调用开始 | `tool_name` |
| `tool_args` | 工具参数 | `tool_args`, `is_streaming_file` |
| `tool_result_start` | 工具结果开始 | `tool_name` |
| `tool_result_content` | 工具结果内容 | `content`, `is_streaming_file` |
| `tool_result_end` | 工具结果结束 | `tool_name` |
| `agent_round` | Agent执行轮次 | `current_round`, `token_usage` |
| `agent_finished` | Agent执行完成 | `data` (执行统计) |
| `error` | 错误事件 | `error_message` |

## 流式文件操作

当Agent执行文件操作时，会有特殊的标识：

```javascript
// 检查是否为流式文件操作
if (event.is_streaming_file) {
    console.log(`文件操作: ${event.operation_mode} -> ${event.file_path}`);
    console.log(`文件内容: ${event.content}`);
}
```

支持的文件操作模式：
- `write`: 覆盖写入
- `append`: 追加写入
- `modify`: 修改指定行
- `insert`: 插入内容

## API接口说明

### 执行Agent任务
```
POST /api/v1/agent/execute/stream
Content-Type: application/json

{
    "query": "任务描述",
    "agent_type": "PlanAgent",
    "max_rounds": 80,
    "stream_file_operations": true,
    "llm_config": {
        "api_key": "your_api_key",
        "base_url": "your_base_url",
        "max_tokens": 64000
    }
}
```

### 获取活跃会话
```
GET /api/v1/agent/sessions
```

### 健康检查
```
GET /api/v1/health
```

## 开发建议

### 1. 错误处理
```javascript
const client = new AgentStreamClient({
    onError: (error) => {
        console.error('流式连接错误:', error);
        // 显示用户友好的错误信息
        showErrorMessage(error.message);
    }
});
```

### 2. 连接状态管理
```javascript
const client = new AgentStreamClient({
    onConnect: () => {
        setConnectionStatus('已连接');
        enableUI();
    },
    onDisconnect: () => {
        setConnectionStatus('已断开');
        disableUI();
    }
});
```

### 3. 内存管理
```javascript
// 限制事件历史数量，避免内存泄漏
const MAX_EVENTS = 1000;
if (events.length > MAX_EVENTS) {
    setEvents(prev => prev.slice(-MAX_EVENTS));
}
```

### 4. 性能优化
```javascript
// 使用React.memo优化渲染
const EventItem = React.memo(({ event }) => {
    return <div>{event.content}</div>;
});

// 虚拟滚动处理大量事件
import { FixedSizeList as List } from 'react-window';
```

## 自定义扩展

### 添加新的事件处理
```javascript
class CustomEventHandler extends AgentEventHandler {
    onCustomEvent(event) {
        // 处理自定义事件
    }
}
```

### 自定义UI主题
```css
.agent-stream-component {
    --primary-color: #007bff;
    --success-color: #28a745;
    --error-color: #dc3545;
    --background-color: #f8f9fa;
}
```

## 故障排除

### 常见问题

1. **连接失败**
   - 检查后端API服务是否启动
   - 确认baseUrl配置正确
   - 检查CORS设置

2. **事件解析失败**
   - 检查JSON格式是否正确
   - 确认事件类型是否支持

3. **文件操作不显示**
   - 确认`stream_file_operations`为true
   - 检查`is_streaming_file`字段

4. **内存占用过高**
   - 限制事件历史数量
   - 定期清理不需要的数据

### 调试技巧

```javascript
// 启用详细日志
const client = new AgentStreamClient({
    onEvent: (event) => {
        console.log('事件详情:', JSON.stringify(event, null, 2));
    }
});

// 监控连接状态
client.addEventListener('statechange', (state) => {
    console.log('连接状态变化:', state);
});
```

## 许可证

MIT License - 可自由使用和修改。
