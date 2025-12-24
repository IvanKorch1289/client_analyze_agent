# Analyze Agent - Client Analysis System

## Overview
A multi-agent system for analyzing potential clients and counterparties using LLM, LangGraph, and external data sources. The system provides risk assessment, company data aggregation, and report generation.

## Architecture
- **Backend**: FastAPI on port 8000
- **Frontend**: Streamlit on port 5000 (exposed to web)
- **Both started via**: `python run.py`

## Key Technologies
- **LLM**: OpenRouter (Claude 3.5 Sonnet by default)
- **Agent Framework**: LangGraph
- **Search APIs**: Perplexity AI, Tavily
- **Data Sources**: DaData, Casebook, InfoSphere (Russian company registries)
- **Cache**: Tarantool (with in-memory fallback)

## Project Structure
```
app/
  agents/        - LangGraph agents (orchestrator, search, analyzer)
  api/routes/    - FastAPI endpoints
  config/        - Configuration and settings
  frontend/      - Streamlit UI
  mcp_server/    - MCP server for IDE integration
  services/      - External service clients
  storage/       - Tarantool client and repositories
  shared/        - Shared utilities and config
  utility/       - Helpers, decorators, logging
```

## Running the Application
The workflow `Start application` runs `python run.py` which starts:
1. FastAPI backend on port 8000
2. Streamlit frontend on port 5000

## Configuration
Configuration is loaded from:
1. `config/app.dev.yaml` - Development settings
2. Environment variables (see `.env.example`)

### Required Environment Variables (for full functionality)
- `OPENROUTER_API_KEY` - LLM access
- `PERPLEXITY_API_KEY` - Web search
- `TAVILY_API_KEY` - Extended search
- `DADATA_API_TOKEN`, `DADATA_API_SECRET` - Company data (Russia)
- `CASEBOOK_API_KEY` - Legal cases
- `INFOSFERA_API_KEY` - Additional analytics

### Optional
- `ADMIN_TOKEN` - For administrative UI functions
- `TARANTOOL_HOST/PORT` - Cache (uses in-memory fallback if unavailable)

## Development Notes
- All API keys are optional in development mode
- Tarantool uses in-memory fallback when not available
- Security headers and CORS are configured for Replit proxy environment
- Frontend lib modules created in `app/frontend/lib/` for formatters, UI helpers, validators

## Recent Changes (December 2025)
- Made all external API keys optional for development
- Created missing `app/frontend/lib/` modules (formatters, ui, validators)
- Configured trusted hosts and CORS for Replit environment
- Set up workflow for port 5000 (Streamlit frontend)

### December 24, 2025 - Risk Scoring and Analyzer Roles Refactor
- **RiskScoreCalculator** (`app/agents/risk_calculator.py`): New normalized scoring system
  - Category weights: Legal 35%, Financial 30%, Reputation 20%, Regulatory 15%
  - Maximum scores per category: Legal 40, Financial 30, Reputation 20, Regulatory 15
  - Key fix: 100 court cases now equals ~24 points (not inflated 75 points)
  - Formula: `final_score = (raw_score / max_possible) * 100`
- **New Analyzer Roles** (`app/mcp_server/prompts/system_prompts.py`):
  - `REGISTRY_ANALYZER`: Analyzes DaData, Casebook, InfoSphere data (official registries)
  - `WEB_ANALYZER`: Analyzes Perplexity, Tavily results (web search & reputation)
  - `MASTER_SYNTHESIZER`: Combines Registry (70%) + Web (30%) into final assessment
- **Feedback Mechanism** (`app/frontend/tabs/analysis.py`):
  - Rating options: Точный / Частично точный / Неточный
  - Optional comment field for user feedback
  - Re-analysis workflow with additional context injection
- All prompts and docstrings converted to Russian language
