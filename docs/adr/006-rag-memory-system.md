# ADR-006: RAG (Retrieval Augmented Generation) Memory System

## Status
Proposed

## Context

The Client Analysis Agent currently performs 1000+ client analyses stored in Tarantool. Each analysis contains:
- Findings and risk assessments (0-100 score)
- Legal cases, financial data, reputational factors
- Citations from 5+ external sources
- Metadata (INN, client_name, timestamps)

**Current limitations:**
1. **No historical context**: When analyzing a client again, the system starts fresh without referencing past analyses
2. **No pattern recognition**: Cannot identify companies with similar risk profiles
3. **No affiliation detection**: Cannot detect related companies (same directors/addresses)
4. **Limited LLM context**: Max 6000 tokens, only current data
5. **Lexical search only**: No semantic understanding of queries

**Expected benefits from RAG:**
- 15-25% improvement in analysis accuracy (similar case context)
- 30-40% faster analysis for repeat clients
- Cross-company risk correlation and prediction
- Enhanced knowledge base from 1000+ historical analyses

## Decision

Implement a **RAG Memory System** with vector embeddings stored in Tarantool, using sentence-transformers for Russian language support.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLIENT ANALYSIS WORKFLOW                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ Orchestrator│───▶│Data Collector│───▶│ RAG-Enhanced Report │  │
│  │   (search   │    │  (5+ sources│    │      Analyzer        │  │
│  │   intents)  │    │   parallel) │    │                      │  │
│  └─────────────┘    └─────────────┘    └──────────┬──────────┘  │
│                                                   │              │
│                                    ┌──────────────▼──────────┐  │
│                                    │   RAG Context Builder   │  │
│                                    │   - Similar analyses    │  │
│                                    │   - Risk patterns       │  │
│                                    │   - Affiliation graph   │  │
│                                    └──────────────┬──────────┘  │
│                                                   │              │
│  ┌───────────────────────────────────────────────▼───────────┐  │
│  │                  TARANTOOL STORAGE                         │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │  │
│  │  │ threads  │  │ reports  │  │  cache   │  │ vectors   │  │  │
│  │  │ (history)│  │ (TTL 30d)│  │ (TTL 1h) │  │(embeddings)│  │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation Components

#### 1. Embedding Service (`app/services/embedding_service.py`)

```python
from sentence_transformers import SentenceTransformer

class EmbeddingService:
    """Service for generating and managing text embeddings."""

    def __init__(self):
        # Use Russian-optimized model
        self.model = SentenceTransformer('intfloat/multilingual-e5-base')

    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding for text."""
        return self.model.encode(text, normalize_embeddings=True).tolist()

    async def embed_analysis(self, analysis: Dict) -> List[float]:
        """Generate embedding for full analysis document."""
        # Combine key fields for comprehensive embedding
        doc_text = f"""
        Client: {analysis.get('client_name', '')}
        INN: {analysis.get('inn', '')}
        Risk Level: {analysis.get('risk_level', '')}
        Findings: {' '.join(str(f) for f in analysis.get('findings', []))}
        Summary: {analysis.get('summary', '')}
        """
        return await self.embed_text(doc_text)
```

#### 2. Vector Repository (`app/storage/repositories/vector_repository.py`)

```python
class VectorRepository:
    """Repository for storing and searching vector embeddings."""

    SPACE_NAME = "vectors"

    async def store_embedding(
        self,
        doc_id: str,
        embedding: List[float],
        metadata: Dict[str, Any],
        doc_type: str = "analysis"
    ) -> str:
        """Store embedding with metadata."""
        # Store in Tarantool with vector index

    async def search_similar(
        self,
        query_embedding: List[float],
        k: int = 5,
        doc_type: Optional[str] = None,
        filters: Optional[Dict] = None
    ) -> List[SimilarResult]:
        """Find k most similar documents."""
        # Use HNSW index for fast approximate nearest neighbor search

    async def batch_embed_existing(self, batch_size: int = 100) -> int:
        """Embed all existing analyses (migration script)."""
```

#### 3. RAG Context Builder (`app/agents/rag_context.py`)

```python
class RAGContextBuilder:
    """Build enriched context for LLM using RAG."""

    async def get_similar_analyses(
        self,
        client_name: str,
        inn: str,
        current_findings: List[str],
        k: int = 3
    ) -> List[Dict]:
        """Find similar past analyses for context."""

    async def find_affiliated_companies(
        self,
        directors: List[str],
        addresses: List[str],
        max_depth: int = 2
    ) -> List[Dict]:
        """Graph search for related companies."""

    async def get_risk_patterns(
        self,
        risk_factors: Dict,
        industry: str,
        k: int = 10
    ) -> Dict:
        """Find similar risk patterns and outcomes."""

    async def build_enhanced_context(
        self,
        state: ClientAnalysisState
    ) -> str:
        """Build full RAG-enhanced context for LLM."""
        similar = await self.get_similar_analyses(...)
        affiliations = await self.find_affiliated_companies(...)
        patterns = await self.get_risk_patterns(...)

        return self._format_context(similar, affiliations, patterns)
```

#### 4. Enhanced Report Analyzer Integration

```python
# In app/agents/report_analyzer.py

async def create_report_with_rag(state: ClientAnalysisState) -> Dict:
    """Create report with RAG-enhanced context."""

    # Get RAG context
    rag_builder = RAGContextBuilder()
    enhanced_context = await rag_builder.build_enhanced_context(state)

    # Build prompt with RAG context
    prompt = f"""
    {SYSTEM_PROMPT}

    ## HISTORICAL CONTEXT (RAG)
    {enhanced_context}

    ## CURRENT ANALYSIS DATA
    {format_source_data(state['source_data'])}

    Analyze the client using both historical patterns and current data.
    """

    # Generate report
    return await llm.analyze(prompt)
```

### Tarantool Vector Space Schema

```lua
-- Create vectors space with HNSW index
box.schema.space.create('vectors', {
    format = {
        {name = 'id', type = 'string'},
        {name = 'doc_type', type = 'string'},  -- 'analysis', 'company', 'person'
        {name = 'doc_id', type = 'string'},     -- reference to source document
        {name = 'embedding', type = 'array'},   -- float vector (768 dims)
        {name = 'metadata', type = 'map'},      -- searchable metadata
        {name = 'created_at', type = 'number'},
    }
})

-- HNSW index for vector similarity search
box.space.vectors:create_index('embedding_idx', {
    type = 'hnsw',
    parts = {{'embedding', 'array'}},
    hnsw = {
        dim = 768,                -- multilingual-e5-base dimension
        distance = 'cosine',
        ef_construction = 128,
        m = 16
    }
})

-- Secondary indexes for filtering
box.space.vectors:create_index('doc_type_idx', {
    type = 'tree',
    parts = {'doc_type'}
})
```

### API Endpoints

```python
# New RAG-related endpoints

@router.get("/rag/similar/{report_id}")
async def find_similar_reports(report_id: str, k: int = 5):
    """Find similar past analyses to a given report."""

@router.post("/rag/search")
async def semantic_search(query: str, doc_type: str = None, k: int = 10):
    """Semantic search across all stored analyses."""

@router.get("/rag/affiliations/{inn}")
async def find_affiliations(inn: str, max_depth: int = 2):
    """Find companies affiliated with given INN."""

@router.post("/rag/reindex")
async def reindex_embeddings(batch_size: int = 100):
    """Reindex all existing documents (admin only)."""
```

## Consequences

### Positive
- **Improved Analysis Quality**: Historical context leads to more accurate assessments
- **Faster Repeat Analysis**: Previous findings immediately available
- **Risk Pattern Detection**: Identify companies with similar risk profiles
- **Affiliation Discovery**: Detect related companies through shared attributes
- **Knowledge Accumulation**: System learns from every analysis
- **Regulatory Compliance**: Better audit trail with historical references

### Negative
- **Increased Complexity**: New service layer to maintain
- **Storage Requirements**: ~3KB per embedding × 10K documents = 30MB minimum
- **Latency Overhead**: 50-100ms for embedding generation + search
- **Cold Start**: Need to embed 1000+ existing analyses
- **Model Dependency**: Requires sentence-transformers model (400MB)

### Mitigations
- Async embedding generation (non-blocking)
- Caching of frequent queries
- Batch processing for cold start migration
- Lazy loading of embedding model
- Fallback to non-RAG mode if service unavailable

## Dependencies

### Python Packages
```toml
# pyproject.toml additions
sentence-transformers = "^2.7.0"
numpy = "^1.26.0"
```

### Tarantool
- Version 3.0+ (for HNSW vector index support)
- Or use external vector DB (Chroma, Weaviate) as alternative

## Alternatives Considered

### External Vector Database (Pinecone/Chroma/Weaviate)
- **Pros**: Optimized for vector search, managed service option
- **Cons**: Additional infrastructure, network latency, vendor lock-in
- **Decision**: Start with Tarantool HNSW, migrate if performance insufficient

### OpenAI Embeddings
- **Pros**: High quality, easy integration
- **Cons**: API costs, data leaves premises (152-FZ compliance)
- **Decision**: Use local sentence-transformers for data privacy

### Fine-tuned Russian Model
- **Pros**: Better accuracy for Russian text
- **Cons**: Training effort, maintenance burden
- **Decision**: Start with multilingual model, fine-tune later if needed

### Knowledge Graph (Neo4j)
- **Pros**: Powerful relationship queries
- **Cons**: Additional database to maintain, learning curve
- **Decision**: Implement graph queries in Tarantool first, consider Neo4j for complex cases

## Implementation Plan

### Phase 1: Foundation (Week 1-2)
1. Add sentence-transformers dependency
2. Implement EmbeddingService
3. Create vectors space in Tarantool
4. Batch embed existing analyses

### Phase 2: Core RAG (Week 3-4)
1. Implement VectorRepository
2. Integrate RAG into Report Analyzer
3. Add similar analyses to LLM context
4. A/B test analysis quality

### Phase 3: Advanced Features (Week 5-6)
1. Affiliation detection (graph queries)
2. Risk pattern recognition
3. Multi-thread conversation memory
4. API endpoints for RAG search

### Phase 4: Optimization (Ongoing)
1. Monitor embedding quality metrics
2. Fine-tune model on domain data
3. Optimize Tarantool indexes
4. Add RAG quality dashboard

## References

- [sentence-transformers](https://www.sbert.net/)
- [multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base)
- [Tarantool HNSW Index](https://www.tarantool.io/en/doc/latest/reference/reference_lua/box_index/hnsw/)
- [RAG Pattern](https://www.pinecone.io/learn/retrieval-augmented-generation/)
