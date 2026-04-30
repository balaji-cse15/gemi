"""Tool registry — all tools registered and discoverable."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

# --- File & navigation tools ---
from .file_read import FileReadTool
from .file_write import FileWriteTool
from .file_edit import FileEditTool
from .file_delete import FileDeleteTool
from .file_move import FileMoveTool
from .file_copy import FileCopyTool
from .glob_tool import GlobTool
from .grep import GrepTool
from .tree import TreeTool
from .diff import DiffTool
from .multi_edit import MultiEditTool

# --- Shell & execution tools ---
from .bash import BashTool
from .powershell import PowerShellTool
from .cmd import CmdTool
from .shell import ShellTool
from .git import GitTool
from .python_run import PythonTool
from .pip_tool import PipTool
from .npm import NpmTool
from .docker import DockerTool
from .task_runner import TaskRunnerTool

# --- Data & encoding tools ---
from .json_tool import JsonTool
from .yaml_tool import YamlTool
from .toml_tool import TomlTool
from .xml_tool import XmlTool
from .csv_tool import CsvTool
from .hash_tool import HashTool
from .base64_tool import Base64Tool
from .regex_tool import RegexTool
from .template_tool import TemplateTool
from .markdown_tool import MarkdownTool
from .encode_tool import EncodeTool
from .notebook import NotebookTool

# --- Web & network tools ---
from .web_fetch import WebFetchTool
from .web_search import WebSearchTool
from .http import HttpTool
from .download import DownloadTool
from .port_scan import PortScanTool
from .dns_tool import DnsLookupTool
from .url_tool import UrlTool

# --- Security & crypto tools ---
from .jwt_tool import JwtTool
from .uuid_tool import UuidTool
from .secrets_gen import SecretsGenTool
from .dotenv_tool import DotenvTool

# --- YOLO security tools (dangerous) ---
from .hash_crack import HashCrackTool
from .crypto_tool import CryptoTool
from .forensics_tool import ForensicsTool
from .payload_gen import PayloadGenTool
from .header_analysis import HeaderAnalysisTool
from .subdomain_tool import SubdomainTool
from .whois_tool import WhoisTool
from .stego_tool import StegoTool

# --- System tools ---
from .system_info import SystemInfoTool
from .env import EnvTool
from .process import ProcessTool
from .archive import ArchiveTool
from .clipboard import ClipboardTool
from .screenshot import ScreenshotTool
from .watch_tool import WatchTool
from .timestamp_tool import TimestampTool
from .math_tool import MathTool

# --- Developer productivity tools ---
from .think_tool import ThinkTool
from .snippet_tool import SnippetTool
from .benchmark_tool import BenchmarkTool
from .dependency_tool import DependencyTool
from .scaffold_tool import ScaffoldTool

# --- Analysis tools ---
from .code_analysis import CodeAnalysisTool
from .sqlite_tool import SqliteTool

# --- Multi-agent orchestration tools ---
from .agent_call import AgentCallTool, AgentVoteTool
from .task import TaskTool
from .todo import TodoWriteTool

# --- Free public-API tools (no keys needed) ---
from .free_apis import FREE_API_TOOLS

# --- Offensive security / pentest / CTF tools (YOLO tier) ---
from .exploits import ExploitsTool
from .recon import RECON_TOOLS
from .cipher import CIPHER_TOOLS
from .hash_id import HASH_TOOLS
from .web_security import WEBSEC_TOOLS
from .api_test import API_TEST_TOOLS

ALL_TOOLS: list[Tool] = [
    # File & navigation (11)
    FileReadTool(),
    FileWriteTool(),
    FileEditTool(),
    FileDeleteTool(),
    FileMoveTool(),
    FileCopyTool(),
    GlobTool(),
    GrepTool(),
    TreeTool(),
    DiffTool(),
    MultiEditTool(),
    # Shell & execution (10)
    BashTool(),
    PowerShellTool(),
    CmdTool(),
    ShellTool(),
    GitTool(),
    PythonTool(),
    PipTool(),
    NpmTool(),
    DockerTool(),
    TaskRunnerTool(),
    # Data & encoding (12)
    JsonTool(),
    YamlTool(),
    TomlTool(),
    XmlTool(),
    CsvTool(),
    HashTool(),
    Base64Tool(),
    RegexTool(),
    TemplateTool(),
    MarkdownTool(),
    EncodeTool(),
    NotebookTool(),
    # Web & network (7)
    WebFetchTool(),
    WebSearchTool(),
    HttpTool(),
    DownloadTool(),
    PortScanTool(),
    DnsLookupTool(),
    UrlTool(),
    # Security & crypto (4)
    JwtTool(),
    UuidTool(),
    SecretsGenTool(),
    DotenvTool(),
    # YOLO security (8)
    HashCrackTool(),
    CryptoTool(),
    ForensicsTool(),
    PayloadGenTool(),
    HeaderAnalysisTool(),
    SubdomainTool(),
    WhoisTool(),
    StegoTool(),
    # System (9)
    SystemInfoTool(),
    EnvTool(),
    ProcessTool(),
    ArchiveTool(),
    ClipboardTool(),
    ScreenshotTool(),
    WatchTool(),
    TimestampTool(),
    MathTool(),
    # Developer productivity (5)
    ThinkTool(),
    SnippetTool(),
    BenchmarkTool(),
    DependencyTool(),
    ScaffoldTool(),
    # Analysis (2)
    CodeAnalysisTool(),
    SqliteTool(),
    # Multi-agent orchestration (4)
    AgentCallTool(),
    AgentVoteTool(),
    TaskTool(),
    TodoWriteTool(),
    # Offensive-security suite
    ExploitsTool(),
] + FREE_API_TOOLS + RECON_TOOLS + CIPHER_TOOLS + HASH_TOOLS + WEBSEC_TOOLS + API_TEST_TOOLS

TOOL_REGISTRY: dict[str, Tool] = {t.name: t for t in ALL_TOOLS}


def get_tool(name: str) -> Tool | None:
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[Tool]:
    return ALL_TOOLS


# Essential tool subset — used for small-context agents (<=12K) so tool
# schemas don't eat the entire context window. Covers file I/O, shell,
# git, reasoning, delegation, web. Curated to mirror Claude Code's
# minimal toolset philosophy.
ESSENTIAL_TOOLS = {
    # File & navigation
    "read_file", "write_file", "edit_file", "glob", "grep", "tree", "diff",
    "multi_edit",
    # Shell
    "bash", "shell", "git", "task_runner",
    # Reasoning + delegation + planning
    "think", "agent_call", "task", "todo_write",
    # Data
    "json_parse",
    # Web
    "web_fetch", "web_search",
}


def tool_schemas(
    exclude_dangerous: bool = False,
    context_budget: int = 0,
    essential_only: bool = False,
) -> list[dict[str, Any]]:
    """Build the tool-schema list to send with each request.

    For small-context agents (context_budget <= 12K) or when
    essential_only=True, returns just the curated essentials plus any
    registered MCP filesystem/memory tools. This keeps the prompt
    overhead under ~3K tokens so the model has room to actually work.
    """
    tools = ALL_TOOLS
    if exclude_dangerous:
        tools = [t for t in tools if not t.dangerous]

    use_essentials = essential_only or (context_budget and context_budget <= 12288)
    if use_essentials:
        # For small-context agents we keep ONLY the curated essentials.
        # MCP tools are too verbose to include here — the agent can still
        # hit them via shell/agent_call/task delegation if needed.
        tools = [t for t in tools if t.name in ESSENTIAL_TOOLS]

    return [t.to_anthropic_schema() for t in tools]


def execute_tool(name: str, workspace: Path, args: dict[str, Any]) -> ToolResult:
    tool = get_tool(name)
    if not tool:
        return ToolResult.fail(f"Unknown tool: {name}")
    return tool.execute(workspace, **args)
