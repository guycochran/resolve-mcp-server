"""Project management tools — list, load, save, create, settings."""

import json
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import get_project_manager, get_project


def register(mcp: FastMCP):

    @mcp.tool()
    def resolve_list_projects() -> str:
        """List all projects in the current database folder.

        Returns a JSON array of project names."""
        pm = get_project_manager()
        projects = pm.GetProjectListInCurrentFolder()
        return json.dumps(projects or [], indent=2)

    @mcp.tool()
    def resolve_load_project(name: str) -> str:
        """Open a project by name.

        Args:
            name: Project name to load.
        """
        pm = get_project_manager()
        project = pm.LoadProject(name)
        if project:
            return f"Opened project: {name}"
        return f"Failed to open project '{name}'. Check the name and make sure no other project is open."

    @mcp.tool()
    def resolve_save_project() -> str:
        """Save the current project."""
        pm = get_project_manager()
        if pm.SaveProject():
            return "Project saved."
        return "Failed to save project."

    @mcp.tool()
    def resolve_create_project(name: str) -> str:
        """Create a new project.

        Args:
            name: Name for the new project.
        """
        pm = get_project_manager()
        project = pm.CreateProject(name)
        if project:
            return f"Created and opened project: {name}"
        return f"Failed to create project '{name}'. A project with that name may already exist."

    @mcp.tool()
    def resolve_get_project_settings() -> str:
        """Get all settings for the current project.

        Returns JSON with frame rate, resolution, color science, and other project settings."""
        project = get_project()
        settings = project.GetSetting("")
        if isinstance(settings, dict):
            return json.dumps(settings, indent=2)
        return json.dumps({"error": "Could not retrieve project settings"})

    @mcp.tool()
    def resolve_set_project_setting(setting: str, value: str) -> str:
        """Set a project setting.

        Args:
            setting: Setting name (e.g., "timelineFrameRate", "timelineResolutionWidth").
            value: Value to set.
        """
        project = get_project()
        if project.SetSetting(setting, value):
            return f"Set {setting} = {value}"
        return f"Failed to set {setting}. Check the setting name and value."
