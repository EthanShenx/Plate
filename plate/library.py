"""Collections of figure workspaces and the tabs open in the workbench."""

import json

from .bundle import write_json
from .model import new_id


class FigureLibrary:
    def __init__(self, workspaces):
        self.path = workspaces / ".projects.json"
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self.projects = data.get("projects", {})
        self.tabs = data.get("tabs", [])
        self.active = data.get("active")
        self.initialized = self.path.is_file()

    def save(self):
        write_json(self.path, {"projects": self.projects, "tabs": self.tabs, "active": self.active})

    def project_for(self, figure):
        return next((key for key, project in self.projects.items() if figure in project["figures"]), None)

    def include(self, figure, name, project_id=None):
        if self.project_for(figure):
            return
        if project_id is None:
            project_id = new_id()
            self.projects[project_id] = {"name": name, "figures": []}
        self.projects[project_id]["figures"].append(figure)

    def untitled_name(self):
        names = {project["name"] for project in self.projects.values() if project["figures"]}
        name = "Untitled project"
        index = 2
        while name in names:
            name = f"Untitled project {index}"
            index += 1
        return name

    def move(self, figure, project_id):
        target = self.projects[project_id]
        original = self.projects[self.project_for(figure)]
        if original is not target:
            original["figures"].remove(figure)
            target["figures"].append(figure)

    def activate(self, figure):
        if figure not in self.tabs:
            self.tabs.append(figure)
        self.active = figure

    def open_project(self, project_id, name, figures, active):
        previous = self.projects, self.tabs, self.active
        self.projects = {**self.projects, project_id: {"name": name, "figures": figures}}
        members = set(figures)
        self.tabs = [figure for figure in self.tabs if figure not in members] + figures
        self.active = active
        try:
            self.save()
        except OSError:
            self.projects, self.tabs, self.active = previous
            raise

    def close(self, figure):
        if figure not in self.tabs:
            return
        index = self.tabs.index(figure)
        self.tabs.remove(figure)
        if self.active == figure:
            self.active = self.tabs[min(index, len(self.tabs) - 1)] if self.tabs else None

    def view(self, figures):
        by_id = {figure["id"]: figure for figure in figures}
        projects = []
        for project_id, project in self.projects.items():
            members = [by_id[figure] for figure in project["figures"] if figure in by_id]
            if members:
                projects.append({"id": project_id, "name": project["name"], "figures": members})
        projects.sort(key=lambda project: max(figure["modified"] for figure in project["figures"]), reverse=True)
        return {"projects": projects, "tabs": [key for key in self.tabs if key in by_id],
                "active": self.active if self.active in by_id else None}
