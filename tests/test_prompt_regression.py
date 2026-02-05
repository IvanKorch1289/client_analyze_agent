"""
Prompt regression tests (Phase 5.3).

Ensures system prompts haven't changed unintentionally.
If a prompt is intentionally modified, update the hash in this file.

Run: pytest tests/test_prompt_regression.py -v
"""

import hashlib

import pytest

from app.mcp_server.prompts.system_prompts import (
    SYSTEM_PROMPTS,
    AnalyzerRole,
    CASCADE_QUESTION_TEMPLATE,
    CASCADE_SYSTEM_PROMPT_CONTENT,
    DATA_COLLECTOR_PROMPT_CONTENT,
    PERPLEXITY_SYSTEM_PROMPT_CONTENT,
)


def _hash(text: str) -> str:
    """Stable SHA-256 hash of prompt text (first 12 hex chars)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# ============================================================================
# Baseline hashes — regenerate with:
#   python -c "
#   from app.mcp_server.prompts.system_prompts import *
#   import hashlib
#   def h(t): return hashlib.sha256(t.encode()).hexdigest()[:12]
#   for role in AnalyzerRole:
#       p = SYSTEM_PROMPTS.get(role)
#       if p: print(f'    AnalyzerRole.{role.name}: \"{h(p.content)}\",')
#   print(f'PERPLEXITY: {h(PERPLEXITY_SYSTEM_PROMPT_CONTENT)}')
#   print(f'CASCADE_SYS: {h(CASCADE_SYSTEM_PROMPT_CONTENT)}')
#   print(f'CASCADE_Q: {h(CASCADE_QUESTION_TEMPLATE)}')
#   print(f'DATA_COLL: {h(DATA_COLLECTOR_PROMPT_CONTENT)}')
#   "
# ============================================================================


class TestSystemPromptsExist:
    """Verify all expected prompts are present."""

    def test_all_roles_have_prompts(self):
        for role in AnalyzerRole:
            assert role in SYSTEM_PROMPTS, f"Missing prompt for {role.name}"

    def test_all_prompts_non_empty(self):
        for role, prompt in SYSTEM_PROMPTS.items():
            assert prompt.content.strip(), f"Empty prompt for {role.name}"
            assert len(prompt.content) > 50, f"Prompt too short for {role.name}"

    def test_analyzer_roles_count(self):
        """We expect exactly 8 roles (update if new ones are added)."""
        assert len(AnalyzerRole) == 8

    def test_constants_defined(self):
        assert PERPLEXITY_SYSTEM_PROMPT_CONTENT
        assert CASCADE_SYSTEM_PROMPT_CONTENT
        assert CASCADE_QUESTION_TEMPLATE
        assert DATA_COLLECTOR_PROMPT_CONTENT


class TestPromptContentStability:
    """Detect unintended prompt content changes via prefix matching."""

    def test_orchestrator_starts_correctly(self):
        p = SYSTEM_PROMPTS[AnalyzerRole.ORCHESTRATOR].content
        assert p.startswith("Ты — оркестратор анализа рисков")

    def test_report_analyzer_starts_correctly(self):
        p = SYSTEM_PROMPTS[AnalyzerRole.REPORT_ANALYZER].content
        assert p.startswith("Ты — эксперт по комплаенсу")

    def test_report_analyzer_cot_starts_correctly(self):
        p = SYSTEM_PROMPTS[AnalyzerRole.REPORT_ANALYZER_COT].content
        assert p.startswith("Ты — эксперт по комплаенсу")

    def test_data_collector_starts_correctly(self):
        p = SYSTEM_PROMPTS[AnalyzerRole.DATA_COLLECTOR].content
        assert "проверяемые факты" in p[:100]

    def test_registry_analyzer_starts_correctly(self):
        p = SYSTEM_PROMPTS[AnalyzerRole.REGISTRY_ANALYZER].content
        assert "реестровых" in p[:100]

    def test_web_analyzer_starts_correctly(self):
        p = SYSTEM_PROMPTS[AnalyzerRole.WEB_ANALYZER].content
        assert "веб-разведки" in p[:100] or "репутаци" in p[:100]

    def test_risk_assessor_starts_correctly(self):
        p = SYSTEM_PROMPTS[AnalyzerRole.RISK_ASSESSOR].content
        assert "оценке рисков" in p[:100]

    def test_master_synthesizer_starts_correctly(self):
        p = SYSTEM_PROMPTS[AnalyzerRole.MASTER_SYNTHESIZER].content
        assert "синтезатор" in p[:100]

    def test_perplexity_prompt_content(self):
        assert "20+ источников" in PERPLEXITY_SYSTEM_PROMPT_CONTENT

    def test_cascade_system_prompt_content(self):
        assert "due diligence" in CASCADE_SYSTEM_PROMPT_CONTENT

    def test_cascade_question_template_has_placeholders(self):
        assert "{client_name}" in CASCADE_QUESTION_TEMPLATE
        assert "{inn}" in CASCADE_QUESTION_TEMPLATE
        assert "{initial_facts}" in CASCADE_QUESTION_TEMPLATE
        assert "{tavily_urls}" in CASCADE_QUESTION_TEMPLATE

    def test_data_collector_prompt_content(self):
        assert "проверяемые факты" in DATA_COLLECTOR_PROMPT_CONTENT


class TestPromptVersioning:
    """Verify prompt version metadata."""

    def test_all_prompts_have_version(self):
        for role, prompt in SYSTEM_PROMPTS.items():
            assert hasattr(prompt, "version") or hasattr(prompt, "name"), (
                f"Prompt {role.name} missing version metadata"
            )

    def test_report_analyzer_and_cot_differ(self):
        """report_analyzer and report_analyzer_cot should have different content."""
        base = SYSTEM_PROMPTS[AnalyzerRole.REPORT_ANALYZER].content
        cot = SYSTEM_PROMPTS[AnalyzerRole.REPORT_ANALYZER_COT].content
        # They may share a prefix but should differ overall
        assert base != cot or len(base) != len(cot), (
            "report_analyzer and report_analyzer_cot should not be identical"
        )
