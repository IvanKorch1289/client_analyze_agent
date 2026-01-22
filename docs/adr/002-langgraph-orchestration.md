# ADR-002: Use LangGraph for multi-agent orchestration

## Status
Accepted

## Context

The Client Analysis Agent requires orchestration of multiple specialized agents:
1. **Orchestrator Agent**: Generates search queries and coordinates workflow
2. **Data Collector Agent**: Fetches data from 7 external sources in parallel
3. **Report Analyzer Agent**: Analyzes collected data and calculates risk scores
4. **File Writer Agent**: Generates PDF/JSON reports

We needed a framework to manage agent state, handle transitions, and support streaming.

## Decision

We chose **LangGraph** (from LangChain ecosystem) for multi-agent orchestration.

### Key reasons:

1. **State Management**: LangGraph provides built-in state management with TypedDict, ensuring type safety across agent transitions.

2. **Graph-Based Workflow**: The directed graph model (nodes + edges) maps naturally to our sequential workflow with conditional branches.

3. **Streaming Support**: Native support for streaming responses, enabling real-time UI updates during long-running analyses.

4. **Checkpointing**: Built-in support for saving/restoring workflow state, useful for debugging and recovery.

5. **LangChain Ecosystem**: Seamless integration with LangChain's LLM abstractions, prompts, and output parsers.

## Consequences

### Positive:
- Clear separation of concerns between agents
- Easy to add new agents or modify workflow
- Built-in support for conditional routing (e.g., skip steps on error)
- Excellent debugging with state inspection at each node
- Streaming enables responsive UI

### Negative:
- Learning curve for graph-based thinking
- Debugging complex graphs can be challenging
- Tight coupling to LangChain ecosystem
- Sequential execution by default (parallelism requires explicit handling)

### Mitigations:
- Created comprehensive documentation for each agent
- Implemented custom logging at graph transitions
- Data collection parallelism handled within Data Collector agent using asyncio.gather()

## Implementation Details

```python
# Simplified workflow graph
workflow = StateGraph(AgentState)

workflow.add_node("orchestrator", orchestrator_agent)
workflow.add_node("data_collector", data_collector_agent)
workflow.add_node("report_analyzer", report_analyzer_agent)
workflow.add_node("file_writer", file_writer_agent)

workflow.set_entry_point("orchestrator")
workflow.add_edge("orchestrator", "data_collector")
workflow.add_edge("data_collector", "report_analyzer")
workflow.add_edge("report_analyzer", "file_writer")
workflow.add_edge("file_writer", END)

app = workflow.compile()
```

## Alternatives Considered

### LangChain Chains (Sequential/Router)
- **Pros**: Simpler API, well-documented
- **Cons**: Less flexible for complex workflows, harder to debug state
- **Rejected because**: Our workflow requires conditional logic and state inspection

### Prefect/Airflow
- **Pros**: Production-grade orchestration, excellent monitoring
- **Cons**: Heavy infrastructure, designed for batch processing not real-time
- **Rejected because**: Overkill for our use case, adds operational complexity

### Custom State Machine
- **Pros**: Full control, no external dependencies
- **Cons**: Significant development effort, need to implement streaming, checkpointing
- **Rejected because**: LangGraph provides these features out of the box

### CrewAI
- **Pros**: Higher-level abstraction for agent collaboration
- **Cons**: Less control over execution flow, newer with less stability
- **Rejected because**: We needed fine-grained control over agent state and transitions
