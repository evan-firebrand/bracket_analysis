"""Tests for the AI evidence packet capture."""
from __future__ import annotations

import json

from core.ai.evidence import (
    MAX_RESULT_SUMMARY_LEN,
    EvidencePacket,
    ToolCallRecord,
    log_audit,
)


class TestEvidencePacketRecord:
    def test_record_truncates_long_result(self):
        packet = EvidencePacket(lens="headline")
        long_json = "x" * (MAX_RESULT_SUMMARY_LEN + 100)
        packet.record("get_pool_state", {}, long_json)

        assert len(packet.tool_calls) == 1
        tc = packet.tool_calls[0]
        assert tc.result_summary.endswith("...[truncated]")
        # truncated body = MAX_RESULT_SUMMARY_LEN chars + suffix
        assert tc.result_summary.startswith("x" * MAX_RESULT_SUMMARY_LEN)

    def test_record_does_not_truncate_short_result(self):
        packet = EvidencePacket(lens="headline")
        short_json = '{"round": 2}'
        packet.record("get_pool_state", {}, short_json)

        assert len(packet.tool_calls) == 1
        assert packet.tool_calls[0].result_summary == short_json
        assert "truncated" not in packet.tool_calls[0].result_summary

    def test_record_exact_boundary_not_truncated(self):
        packet = EvidencePacket(lens="headline")
        boundary_json = "y" * MAX_RESULT_SUMMARY_LEN
        packet.record("tool_a", {}, boundary_json)

        assert packet.tool_calls[0].result_summary == boundary_json
        assert "truncated" not in packet.tool_calls[0].result_summary

    def test_record_preserves_name_and_args(self):
        packet = EvidencePacket(lens="headline")
        packet.record("get_leaderboard", {"limit": 5}, "{}")

        tc = packet.tool_calls[0]
        assert tc.name == "get_leaderboard"
        assert tc.args == {"limit": 5}


class TestScopeBlock:
    def test_empty_packet_scope_block_is_clearly_labeled(self):
        packet = EvidencePacket(lens="headline")
        block = packet.scope_block()

        assert "no tool calls" in block
        assert "SCOPE:" in block
        assert "EXCLUDED:" in block
        assert "CAN CLAIM: nothing" in block
        assert "CANNOT CLAIM:" in block

    def test_scope_block_lists_tool_names(self):
        packet = EvidencePacket(lens="headline")
        packet.record("get_pool_state", {}, "{}")
        packet.record("get_leaderboard", {"limit": 3}, "{}")

        block = packet.scope_block()
        assert "get_pool_state" in block
        assert "get_leaderboard" in block
        assert "SCOPE:" in block
        assert "CAN CLAIM:" in block

    def test_scope_block_dedupes_tool_names(self):
        packet = EvidencePacket(lens="headline")
        packet.record("get_pool_state", {}, "{}")
        packet.record("get_pool_state", {"different": "args"}, "{}")

        block = packet.scope_block()
        # "get_pool_state" should appear in SCOPE line exactly once but call
        # count should reflect both invocations.
        assert block.count("get_pool_state") == 1
        assert "2 tool call(s)" in block


class TestToDict:
    def test_to_dict_is_json_serializable_and_round_trips(self):
        packet = EvidencePacket(lens="headline", viewer="Alice")
        packet.record("get_pool_state", {"foo": "bar"}, '{"round": 2}')
        packet.final_output = "Alice leads!"

        d = packet.to_dict()
        raw = json.dumps(d)
        roundtrip = json.loads(raw)

        assert roundtrip["lens"] == "headline"
        assert roundtrip["viewer"] == "Alice"
        assert roundtrip["final_output"] == "Alice leads!"
        assert len(roundtrip["tool_calls"]) == 1
        assert roundtrip["tool_calls"][0]["name"] == "get_pool_state"
        assert roundtrip["tool_calls"][0]["args"] == {"foo": "bar"}
        assert "scope_block" in roundtrip
        assert "started_at" in roundtrip

    def test_tool_call_record_to_dict(self):
        tc = ToolCallRecord(name="get_pool_state", args={}, result_summary="{}")
        d = tc.to_dict()

        assert d == {"name": "get_pool_state", "args": {}, "result_summary": "{}"}


class TestLogAudit:
    def test_log_audit_writes_file_that_parses_back(self, tmp_path):
        packet = EvidencePacket(lens="recap", viewer="Bob")
        packet.record("get_results", {}, '{"games": []}')
        packet.final_output = "The pool looks exciting."

        path = log_audit(packet, audit_dir=tmp_path)

        assert path.exists()
        assert path.parent == tmp_path
        assert path.suffix == ".json"
        assert "recap" in path.name

        with open(path) as f:
            data = json.load(f)
        assert data["lens"] == "recap"
        assert data["viewer"] == "Bob"
        assert data["final_output"] == "The pool looks exciting."
        assert len(data["tool_calls"]) == 1
        assert data["tool_calls"][0]["name"] == "get_results"

    def test_log_audit_creates_missing_dir(self, tmp_path):
        missing = tmp_path / "nested" / "audit"
        assert not missing.exists()

        packet = EvidencePacket(lens="headline")
        path = log_audit(packet, audit_dir=missing)

        assert missing.exists()
        assert path.parent == missing
        assert path.exists()

    def test_log_audit_accepts_string_dir(self, tmp_path):
        packet = EvidencePacket(lens="headline")
        path = log_audit(packet, audit_dir=str(tmp_path))

        assert path.exists()
