"""
Skill Loader - Automatically scans and loads all Skill plugins in the skills/ directory / 
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
    Automatically scans skills/ directory and loads all Skill plugins. / 
    自动扫描 skills/ 目录，加载所有 Skill 插件。
    Each Skill is a subdirectory containing a skill.py file (implementing BaseSkill). / 
    每个 Skill 是一个子目录，包含 skill.py 文件（实现 BaseSkill 的类）。

    Directory Structure Example / 目录结构示例：
        skills/
        └── smarthome/
            ├── SKILL.md    # Documentation / 文档说明
            └── skill.py    # Implements SmartHomeSkill(BaseSkill) / 实现类
    """

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, BaseSkill] = {}

    def load_all(self, configs: dict = None) -> dict[str, BaseSkill]:
        """
        Scan and load all Skills, returns dictionary of loaded Skills. / 
        扫描并加载所有 Skill，返回已加载的 Skill 字典。
        """
        if not self.skills_dir.exists():
            logger.info(f"[Skill] skills/ directory not found, skipping. / 目录不存在，跳过加载")
            return {}

        configs = configs or {}

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "skill.py"
            if not skill_file.exists():
                continue

            try:
                # Get specific config for this skill / 获取该插件的专属配置
                skill_name = skill_dir.name
                skill_cfg = configs.get(skill_name, {})
                
                skill_instance = self._load_skill_from_file(skill_file, skill_cfg)
                if skill_instance:
                    self._skills[skill_instance.name] = skill_instance
                    logger.info(
                        f"[Skill] Loaded: {skill_instance.name} / 已加载 "
                        f"({len(skill_instance.get_tools())} tools / 个工具)"
                    )
            except Exception as e:
                logger.error(f"[Skill] Failed to load {skill_dir.name}: {e} / 加载失败")

        return self._skills

    def _load_skill_from_file(self, skill_file: Path, config: dict = None) -> BaseSkill | None:
        """
        Dynamically import skill.py, find and instantiate subclass of BaseSkill. / 
        动态导入 skill.py，找到并实例化 BaseSkill 的子类。
        """
        module_name = f"_skill_{skill_file.parent.name}"
        spec = importlib.util.spec_from_file_location(module_name, skill_file)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find classes inheriting from BaseSkill and instantiate / 找到继承了 BaseSkill 的类并实例化
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseSkill)
                and attr is not BaseSkill
            ):
                # Try to instantiate with config if provided / 尝试使用配置实例化
                try:
                    return attr(config=config) if config else attr()
                except TypeError:
                    # Fallback to no-args instantiation if config not accepted / 如果不接受配置参数，回退到无参实例化
                    return attr()

        logger.warning(f"[Skill] BaseSkill subclass not found in {skill_file} / 未找到子类")
        return None

    def get_skill(self, name: str) -> BaseSkill | None:
        """Get a specific loaded skill by name / 根据名称获取已加载的插件实例"""
        return self._skills.get(name)

    def get_all_skills(self) -> dict[str, BaseSkill]:
        return self._skills

    def get_all_tools_openai_format(self) -> list[dict]:
        """
        Get all tools provided by Skills (OpenAI function format). / 
        获取所有 Skill 提供的工具（OpenAI function calling 格式）。
        Tool name format: skill_{skill_name}_{tool_name}
        """
        tools = []
        for skill in self._skills.values():
            for tool in skill.get_tools():
                # Prefix tool names to avoid naming conflicts / 加上前缀避免命名冲突
                tool_copy = dict(tool)
                if "function" in tool_copy:
                    fn = dict(tool_copy["function"])
                    fn["name"] = f"skill_{skill.name}_{fn['name']}"
                    tool_copy["function"] = fn
                tools.append(tool_copy)
        return tools

    async def handle_tool_call(self, full_tool_name: str, arguments: dict) -> str:
        """
        Route tool call to corresponding Skill based on full name. / 
        通过完整工具名路由到对应 Skill 处理。

        Args:
            full_tool_name: e.g., skill_smarthome_control_device
            arguments: Tool arguments / 工具参数

        Returns:
            Execution result string / 执行结果字符串
        """
        for skill in self._skills.values():
            if skill.is_my_tool(full_tool_name):
                raw_name = skill.strip_prefix(full_tool_name)
                return await skill.handle_tool_call(raw_name, arguments)

        return f"❌ Skill handling '{full_tool_name}' not found / 未找到对应的 Skill"

    def is_skill_tool(self, tool_name: str) -> bool:
        """Check if a tool name belongs to a Skill / 判断工具名是否属于 Skill 工具"""
        return tool_name.startswith("skill_")

    def list_skills(self) -> list[dict]:
        """List all loaded Skills and their tools / 列出所有已加载的 Skill 及其工具"""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "tools": [t["function"]["name"] for t in skill.get_tools()],
            }
            for skill in self._skills.values()
        ]
