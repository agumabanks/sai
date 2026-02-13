# 🧠 ANTIGRAVITY — Memory System Specification (PostgreSQL)

## 1. OBJECTIVE
Migrate OpenClaw's SQLite-based memory architecture to a high-performance, scalable PostgreSQL backend using `pgvector` and native Full-Text Search (`tsvector`).

---

## 2. SCHEMA DESIGN

### 2.1 Extensions Required
- `vector` (pgvector)
- `uuid-ossp` (for generating memory IDs)

### 2.2 Tables

```sql
-- Track source files for incremental syncing
CREATE TABLE memory_files (
    path TEXT PRIMARY KEY,
    source VARCHAR(50) NOT NULL DEFAULT 'memory', -- 'memory' or 'sessions'
    hash CHAR(64) NOT NULL, -- SHA-256
    mtime BIGINT NOT NULL,
    size INTEGER NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Store text chunks and their vector embeddings
CREATE TABLE memory_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_path TEXT REFERENCES memory_files(path) ON DELETE CASCADE,
    source VARCHAR(50) NOT NULL DEFAULT 'memory',
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536), -- Dimension depends on model (e.g., 1536 for text-embedding-3-small)
    model VARCHAR(100) NOT NULL,
    hash CHAR(64) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Cache embeddings to save API costs
CREATE TABLE memory_embedding_cache (
    hash CHAR(64) NOT NULL,
    model VARCHAR(100) NOT NULL,
    embedding vector(1536) NOT NULL,
    PRIMARY KEY (hash, model)
);
```

### 2.3 Indexes
```sql
-- Vector index for fast similarity search (HNSW or IVFFlat)
CREATE INDEX ON memory_chunks USING hnsw (embedding vector_cosine_ops);

-- Full-text search index
CREATE INDEX ON memory_chunks USING gin(to_tsvector('english', content));
```

---

## 3. SEARCH LOGIC

### 3.1 Vector Search (Cosine Similarity)
```sql
SELECT id, file_path, start_line, end_line, content, 
       (1 - (embedding <=> :query_vec)) AS score
FROM memory_chunks
WHERE model = :model_name
ORDER BY embedding <=> :query_vec
LIMIT :limit;
```

### 3.2 Keyword Search (FTS)
```sql
SELECT id, file_path, start_line, end_line, content,
       ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', :query)) AS rank
FROM memory_chunks
WHERE to_tsvector('english', content) @@ plainto_tsquery('english', :query)
ORDER BY rank DESC
LIMIT :limit;
```

### 3.3 Hybrid Search
Antigravity should implement **Reciprocal Rank Fusion (RRF)** or a weighted merge of the scores from 3.1 and 3.2, mirroring the OpenClaw weight-based approach.

---

## 4. SYNCING STRATEGY (PYTHON)
1. **Discovery**: Walk the `memory/` directory and `.jsonl` session folders.
2. **Delta Check**: For each file, compare `(path, hash, mtime)` against `memory_files`.
3. **Chunking**: Use `RecursiveCharacterTextSplitter` from LangChain or a custom Markdown-aware splitter (OpenClaw uses a regex-based line splitter).
4. **Embedding**: Check `memory_embedding_cache` before calling LLM providers.
5. **Batching**: Use provider-specific batch APIs (e.g., OpenAI Batch or Gemini Batch) for large initial syncs.
