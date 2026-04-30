"""ScaffoldTool — generate project boilerplate and file templates."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

TEMPLATES = {
    "python-package": {
        "description": "Python package with pyproject.toml, src layout, tests",
        "files": {
            "pyproject.toml": '''[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.10"

[project.optional-dependencies]
dev = ["pytest", "ruff"]
''',
            "src/{name}/__init__.py": '"""Package {name}."""\n__version__ = "0.1.0"\n',
            "src/{name}/main.py": '"""Main entry point."""\n\n\ndef main() -> None:\n    print("Hello from {name}")\n\n\nif __name__ == "__main__":\n    main()\n',
            "tests/__init__.py": "",
            "tests/test_main.py": 'from {name}.main import main\n\n\ndef test_main(capsys):\n    main()\n    assert "{name}" in capsys.readouterr().out.lower()\n',
            ".gitignore": "__pycache__/\n*.pyc\ndist/\n*.egg-info/\n.venv/\n",
        },
    },
    "fastapi": {
        "description": "FastAPI project with routes, models, config",
        "files": {
            "app/__init__.py": "",
            "app/main.py": 'from fastapi import FastAPI\n\napp = FastAPI(title="{name}")\n\n\n@app.get("/")\ndef root():\n    return {{"message": "Hello from {name}"}}\n',
            "app/routes/__init__.py": "",
            "app/models/__init__.py": "",
            "app/config.py": 'from pydantic_settings import BaseSettings\n\n\nclass Settings(BaseSettings):\n    app_name: str = "{name}"\n    debug: bool = False\n\n\nsettings = Settings()\n',
            "requirements.txt": "fastapi>=0.100\nuvicorn[standard]\npydantic-settings\n",
            ".gitignore": "__pycache__/\n*.pyc\n.env\n.venv/\n",
        },
    },
    "cli": {
        "description": "Python CLI app with argparse",
        "files": {
            "{name}.py": '''"""CLI tool: {name}."""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="{name}")
    parser.add_argument("input", help="Input file or value")
    parser.add_argument("-o", "--output", help="Output file")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    if args.verbose:
        print(f"Processing {{args.input}}...")

    print(f"Done: {{args.input}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
        },
    },
    "html": {
        "description": "HTML5 page with minimal CSS/JS",
        "files": {
            "index.html": '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name}</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <main>
        <h1>{name}</h1>
        <p>Edit this page to get started.</p>
    </main>
    <script src="app.js"></script>
</body>
</html>
''',
            "style.css": "* { margin: 0; padding: 0; box-sizing: border-box; }\nbody { font-family: system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 2rem; }\n",
            "app.js": "// {name}\nconsole.log('Ready');\n",
        },
    },
}


class ScaffoldTool(Tool):
    name = "scaffold"
    description = (
        "Generate project scaffolding from templates. "
        "Actions: 'create' (generate project), 'list' (show available templates)."
    )
    read_only = False
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'create' or 'list'.",
                "enum": ["create", "list"],
            },
            "template": {
                "type": "string",
                "description": "Template name (for create).",
            },
            "name": {
                "type": "string",
                "description": "Project name (for create).",
            },
            "output_dir": {
                "type": "string",
                "description": "Output directory (default: current workspace).",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "list":
            lines = ["Available templates:"]
            for name, tmpl in TEMPLATES.items():
                files = len(tmpl["files"])
                lines.append(f"  {name:20s} — {tmpl['description']} ({files} files)")
            return ToolResult.ok("\n".join(lines))

        if action == "create":
            template = kwargs.get("template", "")
            name = kwargs.get("name", "myproject")
            output = kwargs.get("output_dir", "")

            if template not in TEMPLATES:
                return ToolResult.fail(f"Unknown template: {template}. Use action='list' to see options.")

            base = (Path(output) if output else workspace) / name
            tmpl = TEMPLATES[template]
            created = []

            for rel_path, content in tmpl["files"].items():
                rel_path = rel_path.replace("{name}", name)
                content = content.replace("{name}", name)
                fp = base / rel_path
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
                created.append(str(fp.relative_to(workspace)))

            return ToolResult.ok(
                f"Created '{name}' from '{template}' ({len(created)} files):\n"
                + "\n".join(f"  {f}" for f in created)
            )

        return ToolResult.fail(f"Unknown action: {action}")
