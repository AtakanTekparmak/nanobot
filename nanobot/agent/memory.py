"""Memory system for persistent agent memory."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.utils.helpers import ensure_dir

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider
    from nanobot.session.manager import Session


class MemoryStore:
    """Multi-file memory: topic files + HISTORY.md log."""

    # Files always loaded into context (small, always relevant)
    ALWAYS_LOAD = ["user.md", "schedule.md", "triggers.md", "INDEX.md"]

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory_dir = ensure_dir(workspace / "memory")
        self.history_file = self.memory_dir / "HISTORY.md"
        self.user_file = self.memory_dir / "user.md"
        self.index_file = self.memory_dir / "INDEX.md"
        self.schedule_file = self.memory_dir / "schedule.md"
        self.triggers_file = self.memory_dir / "triggers.md"

    # --- File access ---

    def read_file(self, name: str) -> str:
        """Read a named memory file.  name is relative to memory/, e.g. 'user.md'."""
        path = self._resolve(name)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def write_file(self, name: str, content: str) -> None:
        """Write (overwrite) a named memory file, creating parent dirs as needed."""
        path = self._resolve(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def list_files(self) -> list[str]:
        """Return all .md files under memory/ (except HISTORY.md), relative paths."""
        results = []
        for p in sorted(self.memory_dir.rglob("*.md")):
            if p.name == "HISTORY.md":
                continue
            results.append(str(p.relative_to(self.memory_dir)))
        return results

    def get_index(self) -> str:
        """Read the INDEX.md catalogue."""
        return self.read_file("INDEX.md")

    def update_index(self, content: str) -> None:
        """Write the INDEX.md catalogue."""
        self.write_file("INDEX.md", content)

    # --- History (unchanged) ---

    def append_history(self, entry: str) -> None:
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    # --- Context (changed) ---

    def get_memory_context(self) -> str:
        """Return always-loaded memory files for injection into every system prompt."""
        parts = []
        for name in self.ALWAYS_LOAD:
            content = self.read_file(name)
            if content:
                # Use the file's own # Title as the section header
                parts.append(content)
        return "\n\n".join(parts) if parts else ""

    # --- Consolidation ---

    async def consolidate(
        self,
        session: Session,
        provider: LLMProvider,
        model: str,
        *,
        archive_all: bool = False,
        memory_window: int = 50,
    ) -> None:
        """Consolidate old messages into memory files via a consolidation subagent."""
        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info("Memory consolidation (archive_all): {} messages", len(session.messages))
        else:
            keep_count = memory_window // 2
            if len(session.messages) <= keep_count:
                return
            if len(session.messages) - session.last_consolidated <= 0:
                return
            old_messages = session.messages[session.last_consolidated : -keep_count]
            if not old_messages:
                return
            logger.info(
                "Memory consolidation: {} to consolidate, {} keep",
                len(old_messages),
                keep_count,
            )

        # Format conversation for the consolidation agent
        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(
                f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}"
            )

        conversation_text = chr(10).join(lines)

        try:
            await self._run_consolidation_agent(provider, model, conversation_text)

            session.last_consolidated = 0 if archive_all else len(session.messages) - keep_count
            logger.info(
                "Memory consolidation done: {} messages processed, last_consolidated={}",
                len(old_messages),
                session.last_consolidated,
            )
        except Exception as e:
            logger.error("Memory consolidation failed: {}", e)

    def _build_consolidation_tools(self) -> ToolRegistry:
        """Build a ToolRegistry with file tools scoped to memory/ + append_history."""
        tools = ToolRegistry()
        tools.register(ReadFileTool(workspace=self.memory_dir, allowed_dir=self.memory_dir))
        tools.register(WriteFileTool(workspace=self.memory_dir, allowed_dir=self.memory_dir))
        tools.register(EditFileTool(workspace=self.memory_dir, allowed_dir=self.memory_dir))
        tools.register(ListDirTool(workspace=self.memory_dir, allowed_dir=self.memory_dir))
        tools.register(AppendHistoryTool(history_file=self.history_file))
        return tools

    async def _run_consolidation_agent(
        self,
        provider: LLMProvider,
        model: str,
        conversation_text: str,
    ) -> None:
        """Run a multi-turn consolidation agent that reads/writes memory files."""

        tools = self._build_consolidation_tools()

        system_prompt = self._build_consolidation_prompt()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"## Conversation to Process\n\n{conversation_text}"},
        ]

        max_iterations = 15
        for iteration in range(max_iterations):
            response = await provider.chat(
                messages=messages,
                tools=tools.get_definitions(),
                model=model,
            )

            if response.has_tool_calls:
                # Append assistant message with tool calls
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]
                messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": tool_call_dicts,
                })

                # Execute each tool call
                for tc in response.tool_calls:
                    # Guard: HISTORY.md is append-only
                    if tc.name in ("write_file", "edit_file"):
                        target = tc.arguments.get("path", "")
                        if "HISTORY.md" in target:
                            result = "Error: HISTORY.md is append-only. Use the append_history tool instead."
                            messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": result})
                            continue
                    result = await tools.execute(tc.name, tc.arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result,
                    })
            else:
                # Agent is done
                break

        logger.info("Consolidation agent completed in {} iterations", iteration + 1)

    def _build_consolidation_prompt(self) -> str:
        """Build the system prompt for the consolidation agent."""
        return f"""# Memory Consolidation Agent

You are a consolidation agent responsible for processing conversation history and
updating the persistent memory system.

## Your Task
1. First, use `list_dir` with path `"."` to see what memory files currently exist.
2. Read relevant files with `read_file` to understand what's already stored.
3. Extract new facts, preferences, relationships, and context from the conversation.
4. Update existing files or create new ones using `write_file` or `edit_file`.
5. After all file updates, use the `append_history` tool to add a history entry.

## Memory Conventions
- All files in `memory/` directory, names use `snake_case.md`
- `user.md` is the root anchor: user profile, preferences, core facts
- Facts use `- key: value` format; prose paragraphs for narrative
- Cross-reference files with `[[filename.md]]` wikilinks
- Each file starts with `# Title` and uses `## Sections`
- HISTORY.md is append-only — use only the `append_history` tool, never `write_file` or `edit_file`
- Keep files focused: one topic per file
- Check what exists before creating duplicates
- `schedule.md` is the calendar file with structure: `## Recurring`, `## Upcoming`, `## Completed`.
  Appointments use format: `- YYYY-MM-DD HH:MM — Description`. Preserve this structure.
- `triggers.md` holds context-triggered reminders. Structure: `## Greetings / Start of Day`,
  `## Locations`, `## Activities`, `## Custom Triggers`. Preserve heading structure.
- When conversation contains appointments/deadlines, update `schedule.md`
- When conversation contains "remind me when...", update `triggers.md`
- In `schedule.md`, move items from `## Upcoming` whose date has passed to `## Completed`.
  Keep only the last 32 completed items; older ones should be summarized in the HISTORY.md
  entry and removed from schedule.md.

## Rules
- Only update files that actually need changes (don't rewrite unchanged files)
- Create new files when a topic deserves its own file
- Always update `user.md` if new user preferences/facts were discovered
- Update INDEX.md to reflect any new or renamed files
- Append exactly one history entry via `append_history` (2-5 sentences, starting with
  [{datetime.now().strftime('%Y-%m-%d %H:%M')}], specific enough for grep)
- Be concise — store facts, not conversation transcripts
- The main agent may also write to memory files during consolidation.
  Read files immediately before writing to minimize overwrite risk.
  Prefer `edit_file` over `write_file` for existing files.

## Workspace
Memory directory: {self.memory_dir}
"""

    # --- Internal ---

    def _resolve(self, name: str) -> Path:
        """Resolve a relative memory file name to an absolute path."""
        # Strip leading memory/ prefix if the caller includes it
        name = name.lstrip("/")
        if name.startswith("memory/"):
            name = name[len("memory/"):]
        return self.memory_dir / name


class AppendHistoryTool(Tool):
    """Append-only tool for HISTORY.md."""

    def __init__(self, history_file: Path):
        self._history_file = history_file

    @property
    def name(self) -> str:
        return "append_history"

    @property
    def description(self) -> str:
        return "Append a timestamped entry to HISTORY.md. Entry should be 2-5 sentences starting with [YYYY-MM-DD HH:MM]."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entry": {
                    "type": "string",
                    "description": "The history entry to append.",
                }
            },
            "required": ["entry"],
        }

    async def execute(self, entry: str, **kwargs: Any) -> str:
        with open(self._history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")
        return "History entry appended successfully."
