# AI助手前端界面

这是一个现代化的AI助手前端界面，支持与后端流式API进行实时交互。

## 功能特性

### 🔄 流式对话
- **真正的流式输出**：AI回复内容逐字符实时显示，提供流畅的对话体验
- **实时状态更新**：显示AI执行状态（思考中、工具调用、执行完成等）
- **工具调用可视化**：清晰展示AI使用的工具和执行结果

### 📁 文件操作展示
- **文件操作卡片**：当AI操作文件时，显示美观的文件卡片
- **侧边栏预览**：点击文件卡片可在侧边栏查看文件内容
- **流式文件内容**：文件内容支持流式显示，实时更新

### 💬 用户交互
- **智能问答**：当AI需要用户输入时，弹出交互窗口
- **多种回答类型**：支持文本输入、选择题、确认等多种交互方式
- **超时处理**：自动处理交互超时情况

### 🎨 现代化UI
- **响应式设计**：适配桌面和移动设备
- **流畅动画**：丰富的过渡动画和加载效果
- **直观图标**：使用Font Awesome图标库
- **渐变配色**：现代化的紫色渐变主题

## 快速开始

### 1. 启动后端API
确保后端API服务正在运行：
```bash
cd /path/to/deepresearch
python backend/api/stream_api.py
```
后端将在 `http://localhost:8000` 启动

### 2. 启动前端服务器
```bash
cd frontend
python server.py
```
前端将在 `http://localhost:3000` 启动

### 3. 访问界面
在浏览器中打开 `http://localhost:3000`

## 使用说明

### 基本对话
1. 在输入框中输入您的问题或需求
2. 点击发送按钮或按回车键
3. AI将开始执行并流式返回结果

### 文件操作
- 当AI操作文件时，会显示文件操作卡片
- 点击文件卡片可在右侧边栏查看文件内容
- 文件内容支持实时更新

### 用户交互
- 当AI需要您的输入时，会弹出交互窗口
- 输入回答后点击"提交"按钮
- 也可以点击"取消"中止交互

## 技术实现

### 流式连接
- 使用 Fetch API 的 ReadableStream 实现真正的流式连接
- 支持 Server-Sent Events (SSE) 格式的数据流
- 自动重连和错误处理

### 事件处理
支持的事件类型：
- `agent_start`: Agent开始执行
- `agent_content`: AI内容输出（流式）
- `tool_call_start`: 工具调用开始
- `tool_result_content`: 工具结果输出（流式）
- `file_operation`: 文件操作事件
- `user_question`: AI提问用户
- `agent_finished`: 执行完成
- `error`: 错误处理

### 流式显示算法
```javascript
// 逐字符显示效果
const typeChar = () => {
    if (index < chars.length) {
        textElement.textContent += chars[index];
        index++;
        setTimeout(typeChar, 20); // 可调整显示速度
    }
};
```

## 文件结构

```
frontend/
├── index.html          # 主页面
├── app.js             # 核心JavaScript逻辑
├── server.py          # 简单HTTP服务器
└── README.md          # 说明文档
```

## 配置选项

### API配置
在 `app.js` 中修改API地址：
```javascript
this.apiBaseUrl = 'http://localhost:8000/api/v1';
```

### 流式显示速度
调整字符显示间隔：
```javascript
setTimeout(typeChar, 20); // 毫秒，数值越小显示越快
```

### 样式定制
所有样式都在 `index.html` 的 `<style>` 标签中，可以根据需要修改：
- 主题颜色：修改渐变色值
- 字体大小：调整 `font-size` 属性
- 动画效果：修改 `@keyframes` 规则

## 浏览器兼容性

- Chrome 85+
- Firefox 80+
- Safari 14+
- Edge 85+

## 故障排除

### 连接失败
1. 检查后端API是否正常运行
2. 确认API地址配置正确
3. 检查浏览器控制台错误信息

### 流式显示异常
1. 检查网络连接稳定性
2. 确认浏览器支持ReadableStream
3. 查看控制台是否有JavaScript错误

### 文件操作不显示
1. 确认后端返回正确的文件事件
2. 检查文件路径格式
3. 验证事件数据结构

## 开发说明

### 添加新的事件类型
1. 在 `handleStreamEvent` 方法中添加新的 case
2. 实现对应的处理函数
3. 更新UI显示逻辑

### 自定义样式
1. 修改CSS变量定义
2. 添加新的动画效果
3. 调整响应式断点

### 扩展功能
1. 添加更多文件类型支持
2. 实现消息历史记录
3. 添加设置面板

## 许可证

MIT License
