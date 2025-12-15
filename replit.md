# GigaChat MCP AI-Agent with Tools and Caching

## Overview
A multi-agent system built with GigaChat (Russian LLM), LangGraph, LangChain, FastAPI, and Streamlit. The system supports tool calling for company analysis via Russian data providers (DaData, InfoSphere, Casebook).

## Project Structure
```
app/
├── main.py            # FastAPI app entry point
├── settings.py        # Configuration settings
├── streamlit_app.py   # Streamlit frontend
├── advanced_funcs/    # Logging utilities
├── agents/            # LangGraph workflow agents
│   ├── workflow.py    # Main agent graph
│   ├── planner.py     # Planning agent
│   ├── executor.py    # Tool execution
│   └── analyzer.py    # Analysis agent
├── api/routes/        # FastAPI API routes
├── server/            # MCP server
├── services/          # HTTP client, data fetching
├── storage/           # Tarantool/in-memory cache
└── templates/         # HTML templates
```

## Architecture
- **Frontend**: Streamlit on port 5000 (0.0.0.0)
- **Backend**: FastAPI on port 8000 (localhost)
- **Cache**: In-memory fallback (Tarantool not available in Replit)

## Running the Application
```bash
python run.py
```

This starts both:
1. Streamlit frontend on port 5000
2. FastAPI backend on port 8000

## Environment Variables (Optional)
The app works without external API keys using mock/fallback behavior:
- `PERPLEXITY_API_KEY` - Perplexity AI for web search
- `INFOSPHERE_LOGIN`, `INFOSPHERE_PASSWORD` - InfoSphere API
- `DADATA_API_KEY` - DaData API
- `CASEBOOK_API_KEY` - Casebook API
- `HUGGING_FACE_TOKEN` - HuggingFace model access
- `GIGACHAT_TOKEN` - GigaChat API

## Perplexity Integration
The app includes Perplexity AI integration for web search capabilities:
- MCP tools: `perplexity_search`, `perplexity_analyze`
- API endpoints: `POST /utility/perplexity/search`, `GET /utility/perplexity/status`
- Client: `app/services/perplexity_client.py`

## Client Analysis Workflow (NEW)
Multi-agent LangGraph workflow for analyzing potential clients/companies:

### Architecture
```
Orchestrator -> Search Agent (parallel) -> Report Analyzer
```

### Agents
1. **Orchestrator** (`app/agents/orchestrator.py`): Validates input and creates 5 search intents
2. **Search Agent** (`app/agents/search.py`): Parallel Perplexity searches with sentiment analysis
3. **Report Analyzer** (`app/agents/report_analyzer.py`): Creates risk assessment (0-100 score)

### API Endpoint
```
POST /agent/analyze-client
{
  "client_name": "Company Name",
  "inn": "1234567890",  // optional
  "additional_notes": "..."  // optional
}
```

### Response
- `session_id`: Unique analysis ID
- `status`: "completed" | "failed"
- `report`: Risk assessment with findings, recommendations, citations
- `summary`: Markdown summary

### Risk Levels
- **low** (0-24): Standard procedure
- **medium** (25-49): Additional verification
- **high** (50-74): Deep investigation required
- **critical** (75-100): Consider rejection

## Recent Changes
- 2025-12-15: Added Client Analysis Multi-Agent Workflow
  - Created Orchestrator, Search, and Report Analyzer agents
  - LangGraph workflow with parallel Perplexity searches
  - Risk assessment with sentiment analysis
  - API endpoint: POST /agent/analyze-client
- 2025-12-15: Added Perplexity AI agent integration
  - Created PerplexityClient service
  - Added MCP tools for search and analysis
  - Added REST API endpoints
- 2025-12-15: Initial Replit setup
  - Made Tarantool optional with in-memory fallback
  - Configured Streamlit to run on port 5000
  - Configured FastAPI backend on port 8000
  - Made all API keys optional with defaults
