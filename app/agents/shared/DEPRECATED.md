# ⚠️ DEPRECATED MODULE

## Status: Being Phased Out

This module (`app/agents/shared/`) is **deprecated** and will be removed in a future version.

## Migration Guide

### Where to find new implementations:

| Old Location | New Location | Notes |
|-------------|--------------|-------|
| `app.agents.shared.utils.truncate` | `app.shared.utils.formatters.truncate` | ✅ Migrated |
| `app.agents.shared.utils.format_ts` | `app.shared.utils.formatters.format_ts` | ✅ Migrated |
| `app.agents.shared.utils.validate_inn` | `app.shared.security.validate_inn` | ✅ Migrated |
| `app.agents.shared.utils.safe_dict_get` | `app.shared.utils.helpers.safe_dict_get` | ✅ Migrated |
| `app.agents.shared.prompts.*` | `app.mcp_server.prompts.system_prompts.*` | ✅ Typed prompts |

### Update your imports:

**Before:**
```python
from app.agents.shared.utils import truncate, validate_inn
from app.agents.shared.prompts import ANALYZER_SYSTEM_PROMPT
```

**After:**
```python
from app.shared.utils.formatters import truncate
from app.shared.security import validate_inn
from app.mcp_server.prompts.system_prompts import AnalyzerRole, get_system_prompt

# Usage:
system_prompt = get_system_prompt(AnalyzerRole.REPORT_ANALYZER)
```

## Files in this module:

- ✅ `llm.py` - Still used (LLM initialization)
- ✅ `schemas.py` - Still used (Pydantic models)
- ⚠️ `utils.py` - **DEPRECATED** (use `app.shared.utils.*`)
- ⚠️ `prompts.py` - **DEPRECATED** (use `app.mcp_server.prompts.*`)

## Timeline

- **2025-12-23**: Deprecation warning added
- **2026-01-XX**: Breaking changes expected
- **2026-02-XX**: Module removal planned

## Questions?

See `REFACTOR_PROGRESS.md` for detailed migration documentation.

