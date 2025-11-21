# tool/planning.py
from typing import Dict, List, Literal, Optional, TYPE_CHECKING
from pathlib import Path

from backend.tools.base import BaseTool, ToolError, ToolCallResult


_PLANNING_TOOL_DESCRIPTION = """
一个规划工具，允许代理创建和管理复杂任务的解决方案。
该工具提供创建计划、更新计划步骤和跟踪进度的功能。
使用该工具时，必须在完成每个步骤后进行标记（mark_step），
然后再继续执行下一个步骤，以确保计划的执行顺序和状态可追踪。
可调度的协作代理包括：
- WEB_SEARCH：负责检索和整理最新的外部信息与数据；
- CONTENT_ANALYSIS：负责阅读、分析已有内容并输出结构化结论；
- TEST_CASE_GENERATE：负责设计测试用例，帮助验证方案或代码；
- CODE_GENERATE：负责编写或补全代码实现具体功能。
- SUMMARY_REPORT: 负责总结任务成果并生成面向用户的成果报告。
"""

AGENT_LIST = ["WEB_SEARCH", "CONTENT_ANALYSIS", "TEST_CASE_GENERATE", "CODE_GENERATE", "SUMMARY_REPORT"]

class PlanningTool(BaseTool):
    """
    一个规划工具，允许代理创建和管理复杂任务的解决方案。
    该工具提供创建计划、更新计划步骤和跟踪进度的功能。
    使用该工具时，必须在完成每个步骤后进行标记（mark_step），
    然后再继续执行下一个步骤，以确保计划的执行顺序和状态可追踪。
    """

    name: str = "planning"
    description: str = _PLANNING_TOOL_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "description": "要执行的命令。可用命令：create（创建）、update（更新）、list（列表）、get（获取）、set_active（设为活跃）、mark_step（标记步骤）、delete（删除）。",
                "enum": [
                    "create",
                    "update",
                    "list",
                    "get",
                    "set_active",
                    "mark_step",
                    "delete",
                ],
                "type": "string",
            },
            "plan_id": {
                "description": "计划的唯一标识符。create、update、set_active、delete、get 和 mark_step 命令都需要此参数。",
                "type": "string",
            },
            "title": {
                "description": "计划的标题。create 命令必需，update 命令可选。",
                "type": "string",
            },
            "steps": {
                "description": "计划步骤的嵌套结构列表。create 命令必需，update 命令可选。格式：[{'步骤总结描述1': [step1, step2, ...]}, {'步骤总结描述2': [step1, step2, ...]}]",
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
            },
            "steps_type": {
                "description": "steps 中每个步骤的类型。create 命令必需。⚠️ 重要：每个组中的类型数量必须与对应的步骤数量完全匹配！格式：[{'步骤总结描述1': [type1, type2, ...]}, {'步骤总结描述2': [type1, type2, ...]}]。例如：如果某组有3个步骤，则必须提供3个对应的类型。",
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            # 动态获取 AgentPools 的值，避免循环导入
                            "enum": AGENT_LIST  # 暂时硬编码，稍后会在运行时更新
                        }
                    }
                }
            },
            "step_index": {
                "description": "要更新的步骤索引（从0开始）。mark_step 命令必需。",
                "type": "integer",
            },
            "step_status": {
                "description": "要为步骤设置的状态。与 mark_step 命令一起使用。",
                "enum": ["not_started", "in_progress", "completed", "blocked"],
                "type": "string",
            },
            "step_notes": {
                "description": "步骤的附加备注。mark_step 命令可选。",
                "type": "string",
            },
        },
        "required": ["command"],
        "additionalProperties": False,
    }
    session_id: str = None
    plans: dict = {}  # Dictionary to store plans by plan_id
    _current_plan_id: Optional[str] = None  # Track the current active plan
    
    def __init__(self, **kwargs):
        """初始化 PlanningTool，动态更新参数中的枚举值"""
        super().__init__(**kwargs)
        # 动态更新 steps_type 参数中的枚举值
        try:
            from backend.agent.schema import AgentPools
            agent_types = AgentPools.to_list()
            # 更新参数定义中的枚举值
            self.parameters["properties"]["steps_type"]["items"]["additionalProperties"]["items"]["enum"] = agent_types
        except ImportError:
            # 如果导入失败，保持默认值
            pass

    async def execute(
        self,
        *,
        command: Literal[
            "create", "update", "list", "get", "set_active", "mark_step", "delete"
        ],
        plan_id: Optional[str] = None,
        title: Optional[str] = None,
        steps: Optional[List[Dict[str, List[str]]]] = None,
        steps_type: Optional[List[Dict[str, List[str]]]] = None,
        step_index: Optional[int] = None,
        step_status: Optional[
            Literal["not_started", "in_progress", "completed", "blocked"]
        ] = None,
        step_notes: Optional[str] = None,
        **kwargs,
    ):
        """
        使用给定的命令和参数执行规划工具。

        参数：
        - command: 要执行的操作
        - plan_id: 计划的唯一标识符
        - title: 计划的标题（用于 create 命令）
        - steps: 计划的分组步骤列表（用于 create 命令）- 格式：[{'group_name': [step1, step2, ...]}, ...]
        - steps_type: 与步骤结构匹配的分组步骤类型列表（用于 create 命令）- 格式：[{'group_name': [type1, type2, ...]}, ...]
        - step_index: 要更新的步骤索引（用于 mark_step 命令）
        - step_status: 要为步骤设置的状态（用于 mark_step 命令）
        - step_notes: 步骤的附加备注（用于 mark_step 命令）
        """

        if command == "create":
            return self._create_plan(plan_id, title, steps, steps_type)
        elif command == "update":
            return self._update_plan(plan_id, title, steps, steps_type)
        elif command == "list":
            return self._list_plans()
        elif command == "get":
            return self._get_plan(plan_id)
        elif command == "set_active":
            return self._set_active_plan(plan_id)
        elif command == "mark_step":
            return self._mark_step(plan_id, step_index, step_status, step_notes)
        elif command == "delete":
            return self._delete_plan(plan_id)
        else:
            raise ToolError(
                f"Unrecognized command: {command}. Allowed commands are: create, update, list, get, set_active, mark_step, delete"
            )

    def _create_plan(
        self, plan_id: Optional[str], title: Optional[str], steps: Optional[List[Dict[str, List[str]]]], steps_type: Optional[List[Dict[str, List[str]]]] = None
    ) -> ToolCallResult:
        """使用给定的ID、标题和步骤创建新计划。"""
        if not plan_id:
            raise ToolError("Parameter `plan_id` is required for command: create")

        if plan_id in self.plans:
            raise ToolError(
                f"A plan with ID '{plan_id}' already exists. Use 'update' to modify existing plans."
            )

        if not title:
            raise ToolError("Parameter `title` is required for command: create")

        if not steps or not isinstance(steps, list):
            raise ToolError(
                "Parameter `steps` must be a non-empty list for command: create"
            )
        
        # Validate the nested structure
        total_steps = 0
        for step_group in steps:
            if not isinstance(step_group, dict):
                raise ToolError(
                    "Each item in `steps` must be a dictionary with format {'group_name': [step1, step2, ...]}"
                )
            for group_name, group_steps in step_group.items():
                if not isinstance(group_steps, list) or not all(isinstance(step, str) for step in group_steps):
                    raise ToolError(
                        f"Steps in group '{group_name}' must be a list of strings"
                    )
                total_steps += len(group_steps)

        if total_steps == 0:
            raise ToolError("At least one step must be provided in the steps groups")

        # Validate steps_type if provided
        if steps_type:
            if not isinstance(steps_type, list):
                raise ToolError("Parameter `steps_type` must be a list")
            
            # Validate that steps_type structure matches steps structure
            if len(steps_type) != len(steps):
                raise ToolError("Parameter `steps_type` must have the same number of groups as `steps`")
            
            for i, (step_group, type_group) in enumerate(zip(steps, steps_type)):
                step_group_names = set(step_group.keys())
                type_group_names = set(type_group.keys())
                
                if step_group_names != type_group_names:
                    raise ToolError(f"Group names in `steps_type[{i}]` must match group names in `steps[{i}]`")
                
                for group_name in step_group_names:
                    steps_in_group = step_group[group_name]
                    types_in_group = type_group[group_name]
                    
                    if len(steps_in_group) != len(types_in_group):
                        raise ToolError(f"Number of types in group '{group_name}' must match number of steps")
                    
                    # Validate each type is in AgentPools
                    # 延迟导入以避免循环导入
                    from backend.agent.schema import AgentPools
                    valid_types = AgentPools.to_list()
                    for step_type in types_in_group:
                        if step_type not in valid_types:
                            raise ToolError(f"Invalid step type '{step_type}' in group '{group_name}'. Valid types: {valid_types}")

        # Create a new plan with initialized step statuses and notes in nested structure
        step_statuses = []
        step_notes = []
        
        for step_group in steps:
            for group_name, group_steps in step_group.items():
                group_statuses = {group_name: ["not_started"] * len(group_steps)}
                group_notes = {group_name: [""] * len(group_steps)}
                step_statuses.append(group_statuses)
                step_notes.append(group_notes)
        
        plan = {
            "plan_id": plan_id,
            "title": title,
            "steps": steps,
            "steps_type": steps_type if steps_type else None,
            "step_statuses": step_statuses,
            "step_notes": step_notes,
        }

        self.plans[plan_id] = plan
        self._current_plan_id = plan_id  # Set as active plan

        return self._format_plan(plan)


    def _update_plan(
        self, plan_id: Optional[str], title: Optional[str], steps: Optional[List[Dict[str, List[str]]]], steps_type: Optional[List[Dict[str, List[str]]]] = None
    ) -> ToolCallResult:
        """使用新的标题、步骤或步骤类型更新现有计划。"""
        if not plan_id:
            raise ToolError("Parameter `plan_id` is required for command: update")

        if plan_id not in self.plans:
            raise ToolError(f"No plan found with ID: {plan_id}")

        plan = self.plans[plan_id]

        if title:
            plan["title"] = title

        if steps:
            if not isinstance(steps, list):
                raise ToolError(
                    "Parameter `steps` must be a list for command: update"
                )
            
            # Validate the nested structure
            total_steps = 0
            for step_group in steps:
                if not isinstance(step_group, dict):
                    raise ToolError(
                        "Each item in `steps` must be a dictionary with format {'group_name': [step1, step2, ...]}"
                    )
                for group_name, group_steps in step_group.items():
                    if not isinstance(group_steps, list) or not all(isinstance(step, str) for step in group_steps):
                        raise ToolError(
                            f"Steps in group '{group_name}' must be a list of strings"
                        )
                    total_steps += len(group_steps)

            # Create new step statuses and notes in nested structure
            new_step_statuses = []
            new_step_notes = []
            
            for step_group in steps:
                for group_name, group_steps in step_group.items():
                    # Try to preserve existing statuses and notes if they exist
                    old_group_statuses = ["not_started"] * len(group_steps)
                    old_group_notes = [""] * len(group_steps)
                    
                    # Look for existing data in the old structure
                    if "step_statuses" in plan:
                        for old_status_group in plan["step_statuses"]:
                            if group_name in old_status_group:
                                old_statuses = old_status_group[group_name]
                                for i, step in enumerate(group_steps):
                                    if i < len(old_statuses):
                                        old_group_statuses[i] = old_statuses[i]
                                break
                    
                    if "step_notes" in plan:
                        for old_notes_group in plan["step_notes"]:
                            if group_name in old_notes_group:
                                old_notes = old_notes_group[group_name]
                                for i, step in enumerate(group_steps):
                                    if i < len(old_notes):
                                        old_group_notes[i] = old_notes[i]
                                break
                    
                    new_step_statuses.append({group_name: old_group_statuses})
                    new_step_notes.append({group_name: old_group_notes})

            plan["steps"] = steps
            plan["step_statuses"] = new_step_statuses
            plan["step_notes"] = new_step_notes

        # Update steps_type if provided
        if steps_type is not None:
            if not isinstance(steps_type, list):
                raise ToolError("Parameter `steps_type` must be a list")
            
            # Validate that steps_type structure matches current steps structure
            current_steps = plan["steps"]
            if len(steps_type) != len(current_steps):
                raise ToolError("Parameter `steps_type` must have the same number of groups as current `steps`")
            
            for i, (step_group, type_group) in enumerate(zip(current_steps, steps_type)):
                step_group_names = set(step_group.keys())
                type_group_names = set(type_group.keys())
                
                if step_group_names != type_group_names:
                    raise ToolError(f"Group names in `steps_type[{i}]` must match group names in current `steps[{i}]`")
                
                for group_name in step_group_names:
                    steps_in_group = step_group[group_name]
                    types_in_group = type_group[group_name]
                    
                    if len(steps_in_group) != len(types_in_group):
                        raise ToolError(f"Number of types in group '{group_name}' must match number of steps")
                    
                    # Validate each type is in AgentPools
                    # 延迟导入以避免循环导入
                    from backend.agent.schema import AgentPools
                    valid_types = AgentPools.to_list()
                    for step_type in types_in_group:
                        if step_type not in valid_types:
                            raise ToolError(f"Invalid step type '{step_type}' in group '{group_name}'. Valid types: {valid_types}")
            
            plan["steps_type"] = steps_type

        return self._format_plan(plan)

    def _list_plans(self) -> ToolCallResult:
        """列出所有可用的计划。"""
        if not self.plans:
            return ToolCallResult(
                output="No plans available. Create a plan with the 'create' command."
            )

        output = "Available plans:\n"
        for plan_id, plan in self.plans.items():
            current_marker = " (active)" if plan_id == self._current_plan_id else ""
            
            # Calculate completed steps from nested structure
            completed = 0
            total = 0
            for step_group in plan["steps"]:
                for group_name, group_steps in step_group.items():
                    total += len(group_steps)
                    
            # Count completed steps from nested status structure
            for status_group in plan["step_statuses"]:
                for group_name, statuses in status_group.items():
                    completed += sum(1 for status in statuses if status == "completed")
                    
            progress = f"{completed}/{total} steps completed"
            output += f"• {plan_id}{current_marker}: {plan['title']} - {progress}\n"

        return output
    
    def _get_plan(self, plan_id: Optional[str]) -> ToolCallResult:
        """获取特定计划的详细信息。"""
        if not plan_id:
            # If no plan_id is provided, use the current active plan
            if not self._current_plan_id:
                raise ToolError(
                    "No active plan. Please specify a plan_id or set an active plan."
                )
            plan_id = self._current_plan_id

        if plan_id not in self.plans:
            raise ToolError(f"No plan found with ID: {plan_id}")

        plan = self.plans[plan_id]
        return self._format_plan(plan)

    def _set_active_plan(self, plan_id: Optional[str]) -> ToolCallResult:
        """将计划设置为活跃计划。"""
        if not plan_id:
            raise ToolError("Parameter `plan_id` is required for command: set_active")

        if plan_id not in self.plans:
            raise ToolError(f"No plan found with ID: {plan_id}")

        self._current_plan_id = plan_id
        return self._format_plan(self.plans[plan_id])
        

    def _mark_step(
        self,
        plan_id: Optional[str],
        step_index: Optional[int],
        step_status: Optional[str],
        step_notes: Optional[str],
    ) -> ToolCallResult:
        """为步骤标记特定状态和可选备注。"""
        if not plan_id:
            # If no plan_id is provided, use the current active plan
            if not self._current_plan_id:
                raise ToolError(
                    "No active plan. Please specify a plan_id or set an active plan."
                )
            plan_id = self._current_plan_id

        if plan_id not in self.plans:
            raise ToolError(f"No plan found with ID: {plan_id}")

        if step_index is None:
            raise ToolError("Parameter `step_index` is required for command: mark_step")

        plan = self.plans[plan_id]

        # Calculate total steps and find the target step
        total_steps = 0
        target_group_index = None
        target_step_index = None
        current_index = 0
        
        for group_idx, step_group in enumerate(plan["steps"]):
            for group_name, group_steps in step_group.items():
                for step_idx in range(len(group_steps)):
                    if current_index == step_index:
                        target_group_index = group_idx
                        target_step_index = step_idx
                        target_group_name = group_name
                        break
                    current_index += 1
                if target_group_index is not None:
                    break
            if target_group_index is not None:
                break
            
        for step_group in plan["steps"]:
            for group_name, group_steps in step_group.items():
                total_steps += len(group_steps)

        if step_index < 0 or step_index >= total_steps:
            raise ToolError(
                f"Invalid step_index: {step_index}. Valid indices range from 0 to {total_steps-1}."
            )

        if step_status and step_status not in [
            "not_started",
            "in_progress",
            "completed",
            "blocked",
        ]:
            raise ToolError(
                f"Invalid step_status: {step_status}. Valid statuses are: not_started, in_progress, completed, blocked"
            )

        # Update the status in the nested structure
        if step_status and target_group_index is not None:
            plan["step_statuses"][target_group_index][target_group_name][target_step_index] = step_status

        # Update the notes in the nested structure
        if step_notes and target_group_index is not None:
            plan["step_notes"][target_group_index][target_group_name][target_step_index] = step_notes

        return self._format_plan(plan)
        

    def _delete_plan(self, plan_id: Optional[str]) -> ToolCallResult:
        """删除计划。"""
        if not plan_id:
            raise ToolError("Parameter `plan_id` is required for command: delete")

        if plan_id not in self.plans:
            raise ToolError(f"No plan found with ID: {plan_id}")

        del self.plans[plan_id]

        # If the deleted plan was the active plan, clear the active plan
        if self._current_plan_id == plan_id:
            self._current_plan_id = None

        return ToolCallResult(output=f"Plan '{plan_id}' has been deleted.")

    def _format_plan(self, plan: Dict) -> str:
        """格式化计划以供显示。"""
        output = f"# {plan['title']}\n"

        # Add each step group with its steps, status and notes
        for group_idx, step_group in enumerate(plan["steps"]):
            for group_name, group_steps in step_group.items():
                output += f"## {group_name}\n"
                
                # Get corresponding statuses and notes for this group
                group_statuses = []
                group_notes = []
                
                # Find matching status group
                if group_idx < len(plan["step_statuses"]):
                    status_group = plan["step_statuses"][group_idx]
                    if group_name in status_group:
                        group_statuses = status_group[group_name]
                
                # Find matching notes group
                if group_idx < len(plan["step_notes"]):
                    notes_group = plan["step_notes"][group_idx]
                    if group_name in notes_group:
                        group_notes = notes_group[group_name]
                
                for step_idx, step in enumerate(group_steps):
                    status = group_statuses[step_idx] if step_idx < len(group_statuses) else "not_started"
                    notes = group_notes[step_idx] if step_idx < len(group_notes) else ""
                    
                    # Map status to symbols
                    status_symbol = {
                        "not_started": "[]",
                        "in_progress": "[x]",
                        "completed": "[√]",
                        "blocked": "[!]",
                    }.get(status, "[]")

                    output += f"- {status_symbol} {step}\n"
                    if notes:
                        output += f"备注: {notes}\n"

        # 获取项目根目录（从当前文件向上两级：backend/tools/ -> backend/ -> project root）
        project_root = Path(__file__).parent.parent.parent
        output_dir = project_root / f"{self.session_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f"TODO.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output)
        
        return output
