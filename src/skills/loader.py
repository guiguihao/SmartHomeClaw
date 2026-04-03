"""
Skill 加载器 - 自动扫描并加载 skills/ 目录下的所有 Skill 插件
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

from src.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SkillLoader:
    """
    自动扫描 skills/ 目录，加载所有 Skill 插件。
    每个 Skill 是一个子目录，包含 skill.py 文件（实现 BaseSkill 的类）。

    目录结构示例：
        skills/
        └── smarthome/
            ├── SKILL.md    # 文档说明
            └── skill.py    # 实现 SmartHomeSkill(BaseSkill)
    """

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, BaseSkill] = {}

    def load_all(self) -> dict[str, BaseSkill]:
        """
        扫描并加载所有 Skill，返回已加载的 Skill 字典。
        """
        if not self.skills_dir.exists():
            logger.info(f"[Skill] skills/ 目录不存在，跳过加载")
            return {}

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "skill.py"
            if not skill_file.exists():
                continue

            try:
                skill_instance = self._load_skill_from_file(skill_file)
                if skill_instance:
                    self._skills[skill_instance.name] = skill_instance
                    logger.info(
                        f"[Skill] 已加载：{skill_instance.name} "
                        f"({len(skill_instance.get_tools())} 个工具)"
                    )
            except Exception as e:
                logger.error(f"[Skill] 加载 {skill_dir.name} 失败: {e}")

        return self._skills

    def _load_skill_from_file(self, skill_file: Path) -> BaseSkill | None:
        """
        动态导入 skill.py，找到并实例化 BaseSkill 的子类。
        """
        module_name = f"_skill_{skill_file.parent.name}"
        spec = importlib.util.spec_from_file_location(module_name, skill_file)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # 找到继承了 BaseSkill 的类并实例化
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseSkill)
                and attr is not BaseSkill
            ):
                return attr()

        logger.warning(f"[Skill] {skill_file} 中未找到 BaseSkill 子类")
        return None

    def get_all_skills(self) -> dict[str, BaseSkill]:
        return self._skills

    def get_all_tools_openai_format(self) -> list[dict]:
        """
        获取所有 Skill 提供的工具（OpenAI function calling 格式）。
        工具名格式：skill_{skill_name}_{tool_name}
        """
        tools = []
        for skill in self._skills.values():
            for tool in skill.get_tools():
                # 在工具名前加上 skill_{name}_ 前缀，避免命名冲突
                tool_copy = dict(tool)
                if "function" in tool_copy:
                    fn = dict(tool_copy["function"])
                    fn["name"] = f"skill_{skill.name}_{fn['name']}"
                    tool_copy["function"] = fn
                tools.append(tool_copy)
        return tools

    async def handle_tool_call(self, full_tool_name: str, arguments: dict) -> str:
        """
        通过完整工具名路由到对应 Skill 处理。

        Args:
            full_tool_name: 如 skill_smarthome_control_device
            arguments: 工具参数

        Returns:
            执行结果字符串
        """
        for skill in self._skills.values():
            if skill.is_my_tool(full_tool_name):
                raw_name = skill.strip_prefix(full_tool_name)
                return await skill.handle_tool_call(raw_name, arguments)

        return f"❌ 未找到处理工具 '{full_tool_name}' 的 Skill"

    def is_skill_tool(self, tool_name: str) -> bool:
        """判断工具名是否属于 Skill 工具"""
        return tool_name.startswith("skill_")

    def list_skills(self) -> list[dict]:
        """列出所有已加载的 Skill 及其工具"""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "tools": [t["function"]["name"] for t in skill.get_tools()],
            }
            for skill in self._skills.values()
        ]
