# SkillManager 使用指南

## 架构设计

SkillManager 采用**延迟加载策略**，为 Agent 提供渐进式的 skill 访问方式：

```
初始化阶段
    ↓
扫描 backend/skills/ 下所有 .md 文件
    ↓
加载所有 skills 的元数据 (name + description from Front Matter)
    ↓ 轻量级，快速启动
Agent/LLM 看到 skills 列表
    ↓
判断是否需要某个 skill
    ↓
按需加载完整 skill 内容
    ↓
执行任务
```

## 文件结构

所有 skills 存储在 `backend/skills/` 目录下，每个 skill 是一个独立的 Markdown 文件。

### Skill 文件格式

每个 `.md` 文件都是一个完整的 skill，包含：

```markdown
---
name: skill_name
description: "Brief description of what this skill does..."
[other metadata...]
---

# Full Content

## How to Use

...detailed documentation...
```

**Front Matter** (YAML)：
- `name`: Skill 的显示名称
- `description`: 简短描述（初始阶段 LLM 看到的）
- 其他可选字段（如 license 等）

**Content** (Markdown)：
- 完整的使用说明
- 示例代码
- 参数说明
- 返回值说明

## 使用方式

### 1. 初始化 SkillManager

```python
from backend.skills import SkillManager

# 默认加载 backend/skills/ 下的所有 skills
manager = SkillManager()

# 或指定自定义目录
manager = SkillManager(skills_dir="/path/to/skills")
```

### 2. 初始阶段：获取 Skills 列表

```python
# 获取所有 skills 的元数据（快速，O(n) 扫描）
skills_metadata = manager.list_skills()

# 返回：
# [
#   {
#     "skill_id": "web_search",
#     "name": "web_search",
#     "description": "Search the web for information..."
#   },
#   {
#     "skill_id": "docx",
#     "name": "docx",
#     "description": "Use this skill whenever the user wants to create..."
#   },
#   ...
# ]
```

Agent/LLM 在这个阶段看到所有可用 skills 及其简短描述，决定是否需要使用某个 skill。

### 3. 按需加载：获取完整 Skill

当 LLM 判断需要使用某个 skill 时，加载其完整内容：

```python
# 加载完整的 skill 内容（延迟加载 + 缓存）
skill = manager.load_skill("web_search")

if skill:
    print(f"Skill: {skill.name}")
    print(f"Full Content:\n{skill.content}")

# 或直接获取 markdown 内容
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
#     {"skill_id": "docx", "name": "docx"},
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
results = manager.search_skills_by_description("document")
```

## 添加新的 Skill

在 `backend/skills/` 目录下创建新的 Markdown 文件：

1. **创建文件**: `new_skill.md`

2. **编写 Front Matter 和内容**：
   ```markdown
   ---
   name: new_skill
   description: "Clear, concise description of what this skill does"
   ---

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

3. **自动发现**：SkillManager 会自动发现并加载新的 skill

## 现有 Skills

### docx.md
Word 文档处理：创建、读取、编辑 .docx 文件

### web_search.md
网络搜索：在网上搜索信息和数据

### code_generation.md
代码生成：根据需求生成代码

## 性能优化

### 初始化快速

- 只读取 Front Matter，O(n) 文件扫描
- 不解析完整内容
- 适合有数百个 skills 的系统

### 内存效率

- 完整 skill 内容只在需要时加载
- 自动缓存已加载的 skills
- 避免加载未使用的 skills

### 性能对比

| 操作 | 耗时 | 内存占用 |
|------|------|---------|
| 初始化（100个 skills） | ~50ms | ~200KB（仅元数据）|
| 加载 1 个 skill | ~5ms | +50KB |
| 列出所有 skills | <1ms | 无新增 |

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
- `content`: 完整 Markdown 内容（Front Matter 之后的部分）
- `file_path`: 源文件路径
- `to_dict()`: 转换为字典

### SkillMetadata

- `skill_id`: Skill ID
- `name`: 名称
- `description`: 描述
- `file_path`: 源文件路径
- `to_dict()`: 转换为字典

