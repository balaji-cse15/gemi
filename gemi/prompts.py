"""User prompt templates — reusable, parameterized prompts.

Templates live as plain text files with optional YAML frontmatter at
~/.gemi/prompt_templates/<name>.md. Variables use Python format-string
syntax: {var}.

Usage from REPL:
    /use review file_path=src/foo.py
    /use commit-msg

Templates can also be invoked with positional args (mapped to {0}, {1}, ...).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEMPLATES_DIR = Path.home() / ".gemi" / "prompt_templates"


@dataclass
class PromptTemplate:
    name: str
    description: str = ""
    body: str = ""
    variables: list[str] = field(default_factory=list)
    path: str = ""


def _ensure_dir() -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    if not list(TEMPLATES_DIR.glob("*.md")):
        _write_examples()


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, m.group(2)


def _detect_variables(body: str) -> list[str]:
    # Find {name} but ignore double-braced {{name}}
    pattern = re.compile(r"(?<!\{)\{([a-zA-Z_]\w*)\}(?!\})")
    return sorted(set(pattern.findall(body)))


def load_template(name: str) -> PromptTemplate | None:
    _ensure_dir()
    candidates = list(TEMPLATES_DIR.glob(f"{name}.md")) + list(TEMPLATES_DIR.glob(f"{name}.txt"))
    if not candidates:
        return None
    path = candidates[0]
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    fm, body = _parse_frontmatter(text)
    return PromptTemplate(
        name=fm.get("name", path.stem),
        description=fm.get("description", ""),
        body=body.strip(),
        variables=_detect_variables(body),
        path=str(path),
    )


def list_templates() -> list[PromptTemplate]:
    _ensure_dir()
    out: list[PromptTemplate] = []
    for path in sorted(TEMPLATES_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
            fm, body = _parse_frontmatter(text)
            out.append(PromptTemplate(
                name=fm.get("name", path.stem),
                description=fm.get("description", ""),
                body=body.strip(),
                variables=_detect_variables(body),
                path=str(path),
            ))
        except Exception:
            continue
    return out


def render(template: PromptTemplate, args: dict[str, Any]) -> tuple[str, str]:
    """Render a template with the given args. Returns (text, error)."""
    body = template.body
    # Substitute {var} occurrences (escape doubled-braces literally)
    def sub(m):
        key = m.group(1)
        if key not in args:
            return f"<{{{key}}} unset>"
        return str(args[key])
    pattern = re.compile(r"(?<!\{)\{([a-zA-Z_]\w*)\}(?!\})")
    rendered = pattern.sub(sub, body)
    rendered = rendered.replace("{{", "{").replace("}}", "}")
    missing = [v for v in template.variables if v not in args]
    err = ""
    if missing:
        err = f"warning: unset variables: {', '.join(missing)}"
    return rendered, err


def parse_args(arg_string: str) -> dict[str, Any]:
    """Parse k=v pairs (and positional args) from a single string."""
    args: dict[str, Any] = {}
    if not arg_string:
        return args
    # Match key=value pairs (value may be quoted)
    pos_idx = 0
    tokens = re.findall(r'(\w+)=("[^"]*"|\'[^\']*\'|\S+)|("[^"]*"|\'[^\']*\'|\S+)', arg_string)
    for tok in tokens:
        if tok[0]:
            key = tok[0]
            val = tok[1].strip("\"'")
            args[key] = val
        else:
            val = tok[2].strip("\"'")
            args[str(pos_idx)] = val
            pos_idx += 1
    return args


# --- Example seeds ---------------------------------------------------

def _write_examples() -> None:
    samples = {
        "review.md": """---
name: review
description: Code review request — reviews a file for bugs, style, and improvements
---
Please review the file `{file_path}` for:

1. Logic bugs and edge cases
2. Code style and clarity
3. Performance concerns
4. Test coverage gaps
5. Security issues

Use the read_file tool first, then provide concrete feedback with line references.
""",
        "commit-msg.md": """---
name: commit-msg
description: Generate a clean commit message from staged changes
---
Run `git diff --staged --stat` and `git diff --staged` to see what's about to be committed.
Then write a clean commit message following these rules:

- Imperative mood ("add", "fix", "remove")
- Subject line under 60 chars
- Optional body explaining WHY (not what — code shows what)
- No "this commit" / "this PR" preamble
- No trailing period in subject
""",
        "explain.md": """---
name: explain
description: Explain how something works, given a file path or symbol
---
Explain how `{target}` works.

If `{target}` is a file path, read the file first and walk through its key
abstractions and control flow.

If `{target}` is a function or class name, use grep to find its definition,
then explain what it does, when to use it, and any subtle behaviors.

Aim for ~3 paragraphs. Be concrete with line references.
""",
        "fix.md": """---
name: fix
description: Diagnose and fix a bug; "fix {error_msg}" or "fix in {file_path}"
---
Diagnose and fix this issue:

{description}

Process:
1. Read the relevant code with read_file
2. Search for related context with grep
3. Form a hypothesis about the root cause
4. Make a minimal targeted fix with edit_file
5. Verify the fix (run tests if available, otherwise check manually)
6. Summarize what was wrong and what you changed
""",
    }
    for name, content in samples.items():
        target = TEMPLATES_DIR / name
        if not target.exists():
            target.write_text(content, encoding="utf-8")
