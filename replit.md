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
- `INFOSPHERE_LOGIN`, `INFOSPHERE_PASSWORD` - InfoSphere API
- `DADATA_API_KEY` - DaData API
- `CASEBOOK_API_KEY` - Casebook API
- `HUGGING_FACE_TOKEN` - HuggingFace model access
- `GIGACHAT_TOKEN` - GigaChat API

## Recent Changes
- 2025-12-15: Initial Replit setup
  - Made Tarantool optional with in-memory fallback
  - Configured Streamlit to run on port 5000
  - Configured FastAPI backend on port 8000
  - Made all API keys optional with defaults
