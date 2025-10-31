# 🤖 AI用户交互功能

这是一个完整的AI用户交互系统，允许AI在执行任务过程中主动询问用户，获取必要的信息或决策。

## 🎯 功能特性

### ✨ 核心功能
- **主动询问**：AI可以在信息不足时主动询问用户
- **多种问题类型**：支持文本输入、单选题、确认题
- **实时交互**：基于流式API的实时问答
- **超时处理**：自动处理用户响应超时
- **会话管理**：支持多会话并发交互
- **前端集成**：美观的问题对话框界面

### 🔧 技术特点
- **异步处理**：基于asyncio的非阻塞交互
- **流式输出**：与现有流式API完美集成
- **状态管理**：完整的交互状态跟踪
- **错误处理**：健壮的异常处理机制
- **扩展性强**：易于添加新的问题类型

## 🏗️ 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   前端界面      │    │   流式API       │    │   Agent执行     │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ 问题对话框  │ │◄──►│ │ 用户回答接口│ │◄──►│ │ 交互工具    │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ 流式显示    │ │◄──►│ │ 流式输出    │ │◄──►│ │ 任务执行    │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                ▲
                                │
                       ┌─────────────────┐
                       │  交互管理器     │
                       │                 │
                       │ ┌─────────────┐ │
                       │ │ 异步等待    │ │
                       │ └─────────────┘ │
                       │ ┌─────────────┐ │
                       │ │ 超时处理    │ │
                       │ └─────────────┘ │
                       │ ┌─────────────┐ │
                       │ │ 会话管理    │ │
                       │ └─────────────┘ │
                       └─────────────────┘
```

## 🚀 快速开始

### 1. 启动后端服务

```bash
cd backend
python api/stream_api.py
```

### 2. 打开前端界面

```bash
cd frontend
python -m http.server 8080
# 访问 http://localhost:8080/frontend_example.html
```

### 3. 测试用户交互

在前端输入一个模糊的任务，比如：
```
帮我做一个测试项目
```

AI会主动询问：
- 要测试什么类型的项目？
- 使用什么测试框架？
- 需要什么配置参数？

## 📋 使用指南

### 在Agent中使用用户交互

```python
# 1. 启用用户交互功能
agent.enable_user_interaction(interaction_manager, session_id)

# 2. 在Agent执行过程中询问用户
async def some_planning_step(self):
    # 选择题
    async for response in self.execute_tool_call("ask_user", {
        "question": "请选择要使用的测试框架？",
        "question_type": "choice",
        "options": ["pytest", "unittest", "nose2"],
        "context": "pytest功能最全面，unittest是标准库，nose2轻量级",
        "timeout": 180,
        "required": True
    }):
        yield response
    
    # 确认题
    async for response in self.execute_tool_call("ask_user", {
        "question": "是否要删除现有的测试文件？",
        "question_type": "confirm",
        "context": "检测到已存在测试文件，删除后将重新生成",
        "timeout": 120,
        "required": True
    }):
        yield response
    
    # 文本输入
    async for response in self.execute_tool_call("ask_user", {
        "question": "请输入API的基础URL地址",
        "question_type": "text",
        "context": "例如：https://api.example.com",
        "timeout": 300,
        "required": True
    }):
        yield response
```

### 问题类型说明

#### 1. 选择题 (choice)
```python
{
    "question": "请选择一个选项",
    "question_type": "choice",
    "options": ["选项1", "选项2", "选项3"],
    "timeout": 180
}
```

#### 2. 确认题 (confirm)
```python
{
    "question": "是否确认执行此操作？",
    "question_type": "confirm",
    "timeout": 120
}
```

#### 3. 文本输入 (text)
```python
{
    "question": "请输入您的回答",
    "question_type": "text",
    "timeout": 300
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | ✅ | 要询问的问题内容 |
| `question_type` | string | ❌ | 问题类型：text/choice/confirm |
| `options` | array | ❌ | 选择题的选项列表 |
| `timeout` | integer | ❌ | 超时时间（秒），默认300 |
| `required` | boolean | ❌ | 是否必须回答，默认true |
| `context` | string | ❌ | 问题的背景说明 |

## 🎨 前端界面

### 问题对话框特性
- **美观设计**：现代化的对话框界面
- **响应式**：适配不同屏幕尺寸
- **实时倒计时**：显示剩余时间
- **类型适配**：根据问题类型显示不同界面
- **键盘支持**：支持回车提交、ESC取消

### 事件类型
- `user_question`：AI询问用户
- `user_answer_received`：收到用户回答
- `interaction_timeout`：交互超时

## 🔧 API接口

### 提交用户回答
```http
POST /api/v1/agent/user-answer
Content-Type: application/json

{
    "session_id": "会话ID",
    "interaction_id": "交互ID", 
    "answer": "用户回答",
    "answer_type": "回答类型"
}
```

### 获取会话交互历史
```http
GET /api/v1/agent/interactions/{session_id}
```

### 获取交互统计
```http
GET /api/v1/agent/interaction-stats
```

## 🧪 测试示例

运行测试示例：
```bash
python test_user_interaction.py
```

测试内容：
1. **不同问题类型测试**：选择题、确认题、文本输入
2. **超时处理测试**：验证超时机制
3. **Agent集成测试**：完整的Agent用户交互流程

## 📝 最佳实践

### 1. 问题设计原则
- **具体明确**：避免模糊的问题
- **提供上下文**：帮助用户理解问题背景
- **合理选项**：选择题提供清晰的选项
- **适当超时**：根据问题复杂度设置超时时间

### 2. 交互时机
- **信息收集阶段**：任务开始前收集必要信息
- **决策分支点**：遇到多种方案选择时
- **确认关键操作**：执行重要操作前确认
- **错误处理**：出现问题时询问处理方式

### 3. 用户体验
- **一次一问**：避免同时询问多个问题
- **渐进式询问**：从简单到复杂逐步询问
- **智能默认值**：为非必填问题提供合理默认值
- **清晰反馈**：及时反馈用户的选择结果

## 🛠️ 扩展开发

### 添加新的问题类型

1. **扩展问题类型枚举**：
```python
# 在 user_interaction.py 中添加
"question_type": {
    "enum": ["text", "choice", "confirm", "number", "date"],  # 添加新类型
}
```

2. **实现验证逻辑**：
```python
def _validate_answer(self, interaction_data: InteractionData, answer: str) -> bool:
    if interaction_data.question_type == "number":
        try:
            float(answer)
            return True
        except ValueError:
            return False
    # ... 其他验证逻辑
```

3. **更新前端界面**：
```javascript
// 在前端添加新的输入组件
if (question_type === 'number') {
    optionsHtml = `
        <input type="number" id="userAnswerInput" placeholder="请输入数字..." />
        <button class="submit-btn" onclick="submitTextAnswer('${interaction_id}')">提交</button>
    `;
}
```

### 自定义交互逻辑

```python
class CustomInteractionTool(UserInteractionTool):
    """自定义交互工具"""
    
    async def execute(self, **kwargs):
        # 添加自定义逻辑
        if kwargs.get("auto_validate"):
            # 自动验证用户输入
            pass
        
        # 调用父类方法
        async for result in super().execute(**kwargs):
            yield result
```

## 🐛 故障排除

### 常见问题

1. **交互无响应**
   - 检查交互管理器是否正确初始化
   - 确认会话ID是否正确设置
   - 查看后端日志是否有错误

2. **前端对话框不显示**
   - 检查事件解析是否正确
   - 确认CSS样式是否加载
   - 查看浏览器控制台错误

3. **超时处理异常**
   - 检查超时时间设置是否合理
   - 确认异步任务是否正确清理
   - 查看交互管理器状态

### 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 查看交互状态
stats = interaction_manager.get_stats()
print(f"交互统计: {stats}")

# 监控会话
interactions = await interaction_manager.get_session_interactions(session_id)
for interaction in interactions:
    print(f"交互: {interaction.question} -> {interaction.answer}")
```

## 📄 许可证

MIT License - 可自由使用和修改。

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个功能！

---

**享受与AI的智能交互体验！** 🎉
