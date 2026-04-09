"""Evidence packet capture for AI agent runs.

Every agent invocation captures an EvidencePacket that records every tool call
(name, args, result summary). Used to:
  1. Show "Show sources" to users below AI-generated content
  2. Auto-generate scope blocks per CLAUDE.md analysis integrity rules
  3. Write audit logs for post-hoc review
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MAX_RESULT_SUMMARY_LEN = 500


@dataclass
class ToolCallRecord:
    name: str
    args: dict
    result_summary: str  # truncated JSON string

    def to_dict(self) -> dict:
        return {"name": self.name, "args": self.args, "result_summary": self.result_summary}


@dataclass
class EvidencePacket:
    lens: str
    viewer: str | None = None
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    final_output: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def record(self, name: str, args: dict, result_json: str) -> None:
        summary = (
            result_json
            if len(result_json) <= MAX_RESULT_SUMMARY_LEN
            else result_json[:MAX_RESULT_SUMMARY_LEN] + "...[truncated]"
        )
        self.tool_calls.append(ToolCallRecord(name=name, args=args, result_summary=summary))

    def scope_block(self) -> str:
        """Auto-generate a scope block from tool calls.

        Returns a multi-line string in CLAUDE.md's SCOPE/EXCLUDED/CAN CLAIM/CANNOT CLAIM format.
        The block describes exactly what data was queried.
        """
        if not self.tool_calls:
            return (
                "SCOPE: (no tool calls)\n"
                "EXCLUDED: all data\n"
                "CAN CLAIM: nothing\n"
                "CANNOT CLAIM: anything requiring data"
            )
        tool_names = sorted({tc.name for tc in self.tool_calls})
        scope_items = ", ".join(tool_names)
        return (
            f"SCOPE: data from tool calls: {scope_items}\n"
            f"EXCLUDED: any data not surfaced by the above tools\n"
            f"CAN CLAIM: conclusions drawn from the {len(self.tool_calls)} tool call(s) above\n"
            f"CANNOT CLAIM: anything about players, teams, or scenarios not queried"
        )

    def to_dict(self) -> dict:
        return {
            "lens": self.lens,
            "viewer": self.viewer,
            "started_at": self.started_at,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "final_output": self.final_output,
            "scope_block": self.scope_block(),
        }


def log_audit(packet: EvidencePacket, audit_dir: Path | str = "data/ai_audit") -> Path:
    """Write the evidence packet to a timestamped audit log file.

    Returns the path written. Safe if audit_dir does not exist.
    """
    audit_dir = Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    path = audit_dir / f"{ts}_{packet.lens}.json"
    with open(path, "w") as f:
        json.dump(packet.to_dict(), f, indent=2, default=str)
    return path
