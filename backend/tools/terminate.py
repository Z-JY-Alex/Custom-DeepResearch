from backend.tools.base import BaseTool


_TERMINATE_DESCRIPTION = """当请求得到满足或助手无法进一步执行任务时终止交互。
当您完成所有任务后，调用此工具来结束工作。"""


class Terminate(BaseTool):
    name: str = "terminate"
    description: str = _TERMINATE_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "交互的完成状态。",
                "enum": ["success", "failure"],
            }
        },
        "required": ["status"],
    }

    async def execute(self, status: str) -> str:
        """完成当前执行"""
        return f"当前任务状态:{status}"