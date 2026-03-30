# SkillManager 使用指南

## 概述

`SkillManager` 是一个新的技能管理系统，与工具层（Tools）并列，为主 Agent（如 PlanAgent）提供高级功能接口。

## 架构

```
PlanAgent (主 Agent)
    ↓
SkillManager (技能管理器)
    ├─ WEB_SEARCH_SKILL      (网络搜索)
    ├─ CODE_ANALYSIS_SKILL   (代码分析)
    ├─ CONTENT_ANALYSIS_SKILL (内容分析)
    ├─ TEST_GENERATION_SKILL  (测试生成)
    ├─ CODE_GENERATION_SKILL  (代码生成)
    ├─ DATA_ANALYSIS_SKILL    (数据分析)
    └─ SUMMARY_SKILL          (总结生成)
```

## 使用方式

### 1. 初始化 SkillManager

```python
from backend.skills import SkillManager

# 创建管理器（可注入依赖）
manager = SkillManager(
    llm_config=llm_config,
    artifact_manager=artifact_manager,
    memory=memory,
    session_id=session_id
)
```

### 2. 获取可用 Skills 列表

```python
# 获取所有 skills 摘要
skills = manager.list_skills()
# [
#   {"skill_id": "web_search", "name": "Web Search", "category": "search", "complexity": "simple", ...},
#   ...
# ]

# 按分类获取
search_skills = manager.get_skills_by_category("search")

# 获取简单的独立 skills
simple_skills = manager.get_simple_skills()

# 获取复杂的需要规划的 skills
complex_skills = manager.get_complex_skills()
```

### 3. 获取 Skill 详情

```python
# 获取具体 skill 的详细信息
details = manager.get_skill_details("web_search")
# {
#   "skill_id": "web_search",
#   "name": "Web Search",
#   "description": "Search the web for information...",
#   "category": "search",
#   "complexity": "simple",
#   "required_params": ["query"],
#   "optional_params": {"topic": "general", ...},
#   "can_be_standalone": True,
#   "requires_planning": False,
#   ...
# }
```

### 4. 检查 Skill 可执行性

```python
# 检查是否可以执行 skill
can_execute, error = await manager.can_execute(
    "web_search",
    query="人工智能最新发展"
)

if not can_execute:
    print(f"无法执行: {error}")
```

### 5. 执行 Skill

```python
# 执行 skill（流式输出）
async for chunk in manager.execute_skill(
    "web_search",
    query="人工智能最新发展",
    topic="general",
    max_results=10
):
    print(chunk)
    # 每个 chunk 是：
    # {"type": "search_started", ...}
    # {"type": "search_results", ...}
    # {"type": "search_completed", ...}
```

### 6. 查找兼容 Skills

```python
# 获取与当前 skill 兼容的其他 skills
compatible = manager.get_compatible_skills("web_search")
# ["content_analysis", "summary"]

# 建议执行完后的下一步
suggestions = manager.suggest_next_skills("web_search")
# [
#   {"skill_id": "content_analysis", "name": "Content Analysis", ...},
#   {"skill_id": "summary", "name": "Summary Generation", ...}
# ]
```

## Skill 分类

### 简单任务 (can_be_standalone = True)

- **Web Search**: 网络搜索
- **Code Analysis**: 代码分析
- **Content Analysis**: 内容分析
- **Summary**: 总结生成

这些 Skill 可以直接由主 Agent 执行，不需要先规划。

### 复杂任务 (requires_planning = True)

- **Test Generation**: 测试用例生成
- **Code Generation**: 代码生成
- **Data Analysis**: 数据分析

这些 Skill 需要先通过 Planning Tool 制定计划后再执行。

## 在 PlanAgent 中的使用

```python
class PlanAgent(BaseAgent):
    def __init__(self, ...):
        super().__init__(...)
        self.skill_manager = SkillManager(
            llm_config=self.llm_config,
            artifact_manager=self.artifact_manager,
            memory=self.memory,
            session_id=self.session_id
        )

    async def run(self, task: str):
        # 获取可用 skills
        simple_skills = self.skill_manager.get_simple_skills()

        # LLM 可以看到 skills 列表并决定：
        # 1. 简单任务直接调用单个 skill
        # 2. 复杂任务先制定计划再调用多个 skills

        # 示例：直接执行简单任务
        if task.startswith("搜索"):
            async for chunk in self.skill_manager.execute_skill("web_search", ...):
                yield chunk

        # 示例：复杂任务需要规划
        elif task.startswith("生成"):
            # 先制定计划
            planning_result = await self.planning_tool(...)

            # 然后依次执行 skills
            for step in plan:
                async for chunk in self.skill_manager.execute_skill(step.skill_id, ...):
                    yield chunk
```

## 扩展自定义 Skill

```python
from backend.skills import BaseSkill, SkillInfo

class CustomSkill(BaseSkill):
    def __init__(self, **context):
        info = SkillInfo(
            skill_id="custom_skill",
            name="Custom Skill",
            description="My custom skill",
            category="custom",
            complexity="medium",
            required_params=["input"],
            optional_params={},
            can_be_standalone=True,
            compatible_skills=["web_search"],
            estimated_time="10-30 seconds",
        )
        super().__init__(info, **context)

    async def execute(self, **kwargs):
        # 实现你的逻辑
        yield {"type": "custom_event", "data": ...}

# 注册到管理器
custom_skill = CustomSkill()
manager.register_skill(custom_skill)
```

## 核心特性

1. **渐进式获取**: 先列出 skills，需要时才获取详情
2. **类型分类**: 简单任务 vs 复杂任务，可独立执行 vs 需要规划
3. **兼容性管理**: 自动识别 skills 之间的组合关系
4. **流式执行**: 所有 skills 都支持异步流式执行
5. **参数验证**: 自动验证必需参数和参数有效性

## 文件结构

```
backend/skills/
├── __init__.py                      # 公开接口
├── base.py                          # BaseSkill, SkillInfo, SkillStatus
├── manager.py                       # SkillManager
├── web_search_skill.py              # Web 搜索技能
├── code_analysis_skill.py           # 代码分析技能
├── content_analysis_skill.py        # 内容分析技能
├── test_generation_skill.py         # 测试生成技能
├── code_generation_skill.py         # 代码生成技能
├── data_analysis_skill.py           # 数据分析技能
└── summary_skill.py                 # 总结生成技能
```
