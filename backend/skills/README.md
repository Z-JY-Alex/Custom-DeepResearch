# SkillManager 使用指南

## 架构设计

SkillManager 采用**延迟加载策略**，优化了大规模 skills 系统的性能：

```
初始化阶段
    ↓
加载所有 skills 的元数据 (name + description)
    ↓ 轻量级数据，快速启动
主 Agent 看到 skills 列表
    ↓
模型判断是否需要某个 skill
    ↓
按需加载完整 skill 内容
    ↓
执行任务
```

## 文件结构

所有 skills 存储在 `backend/skills/docx/` 目录下，每个 skill 是一个 Markdown 文件。

### Skill 文件格式

```markdown
---
name: skill_name
description: "Brief description of what this skill does..."
---

# Full Content

## How to Use

...detailed documentation...
```

**Front Matter** (YAML) 包含：
- `name`: Skill 显示名称
- `description`: 简短描述（LLM 初始阶段看到的）
- 其他可选字段

**Content** (Markdown)：
- 详细的使用说明
- 示例代码
- 参数说明
- 返回值说明

## 使用方式

### 1. 初始化 SkillManager

```python
from backend.skills import SkillManager

# 默认加载 backend/skills/docx 下的所有 skills
manager = SkillManager()

# 或指定自定义目录
manager = SkillManager(skills_dir="/path/to/skills")
```

### 2. 初始阶段：获取 Skills 列表

```python
# 获取所有 skills 的元数据（快速，只含 name 和 description）
skills_metadata = manager.list_skills()

# 返回：
# [
#   {
#     "skill_id": "web_search",
#     "name": "web_search",
#     "description": "Search the web for information..."
#   },
#   ...
# ]
```

LLM 在这个阶段看到所有可用 skills 及其简短描述，决定是否需要使用某个 skill。

### 3. 按需加载：获取完整 Skill

当 LLM 判断需要使用某个 skill 时，加载其完整内容：

```python
# 加载完整的 skill 内容
skill = manager.load_skill("web_search")

if skill:
    print(f"Skill: {skill.name}")
    print(f"Content:\n{skill.content}")

# 或直接获取内容
content = manager.get_skill_content("web_search")
```

### 4. 系统摘要

```python
# 获取系统摘要
summary = manager.get_skills_summary()

# 返回：
# {
#   "total_count": 10,           # 总 skills 数
#   "skills": [                   # 所有 skills 的名称列表
#     {"skill_id": "web_search", "name": "web_search"},
#     ...
#   ],
#   "loaded_count": 2             # 已加载的完整 skills 数
# }
```

### 5. 搜索 Skills

```python
# 按名称搜索
results = manager.search_skills_by_name("search")

# 按描述搜索
results = manager.search_skills_by_description("web")
```

## 集成到 Agent

### PlanAgent 集成示例

```python
from backend.agent import BaseAgent
from backend.skills import SkillManager

class PlanAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.skill_manager = SkillManager()

    async def run(self, task: str):
        # Step 1: 获取所有 skills 的元数据
        available_skills = self.skill_manager.list_skills()

        # Step 2: 将 skills 信息提供给 LLM
        skills_info = "\n".join([
            f"- {s['name']}: {s['description']}"
            for s in available_skills
        ])

        # Step 3: LLM 看到 skills 列表并决定是否使用某个
        llm_response = await self.llm.generate(
            messages=[
                {"role": "system", "content": f"Available skills:\n{skills_info}"},
                {"role": "user", "content": task}
            ]
        )

        # Step 4: 如果 LLM 决定使用某个 skill，加载完整内容
        if "使用 web_search" in llm_response:
            skill = self.skill_manager.load_skill("web_search")
            # 基于 skill.content 执行任务
            ...
```

## 添加新的 Skill

在 `backend/skills/docx/` 目录下创建新的 Markdown 文件：

1. **创建文件**: `new_skill.md`

2. **编写 Front Matter**:
   ```markdown
   ---
   name: new_skill
   description: "Clear, concise description of what this skill does"
   ---
   ```

3. **编写完整内容**:
   ```markdown
   # New Skill

   ## Overview
   Detailed explanation...

   ## When to Use
   - Scenario 1
   - Scenario 2

   ## Usage
   ```code_example```

   ## Parameters
   - param1: description

   ## Returns
   Return value description
   ```

SkillManager 会自动发现并加载新的 skill。

## 性能优化

### 初始化快速

- 只读取 Front Matter，O(n) 文件扫描
- 不解析完整内容
- 适合有数百个 skills 的系统

### 内存效率

- 完整 skill 内容只在需要时加载
- 自动缓存已加载的 skills
- 避免加载未使用的 skills

### 示例性能对比

| 操作 | 耗时 | 内存 |
|------|------|------|
| 初始化（1000个 skills） | ~100ms | ~2MB（仅元数据）|
| 加载 1 个 skill | ~10ms | +50KB |
| 列出所有 skills | ~1ms | 无新增 |

## API 参考

### SkillManager

- `list_skills()` → List[Dict]: 获取所有 skills 元数据
- `get_skill_metadata(skill_id)` → Dict: 获取指定 skill 的元数据
- `has_skill(skill_id)` → bool: 检查 skill 是否存在
- `load_skill(skill_id)` → Skill: 加载完整 skill（延迟加载+缓存）
- `get_skill(skill_id)` → Skill: 获取完整 skill
- `get_skill_content(skill_id)` → str: 获取 skill 的 Markdown 内容
- `search_skills_by_name(keyword)` → List[Dict]: 按名称搜索
- `search_skills_by_description(keyword)` → List[Dict]: 按描述搜索
- `get_skills_summary()` → Dict: 获取系统摘要

### Skill

- `skill_id`: Skill 唯一标识
- `name`: 显示名称
- `description`: 简短描述
- `content`: 完整 Markdown 内容
- `file_path`: 源文件路径
- `to_dict()`: 转换为字典

### SkillMetadata

- `skill_id`: Skill ID
- `name`: 名称
- `description`: 描述
- `file_path`: 源文件路径
- `to_dict()`: 转换为字典
