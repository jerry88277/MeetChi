-- ============================================
-- MeetChi: Enable pgvector Extension & Create Indexes
-- Run this migration after enabling cloudsql.enable_pgvector flag
-- ============================================

-- Step 1: Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Step 2: Vector similarity indexes
-- NOTE: IVFFlat indexes require existing data to build properly.
-- Run these AFTER you have at least ~100 embeddings populated.
-- Until then, the database will use exact (brute-force) search which
-- is perfectly fine for <10K records.

-- Meeting summary embedding index (cosine similarity)
-- CREATE INDEX IF NOT EXISTS idx_meetings_summary_embedding
-- ON meetings USING ivfflat (summary_embedding vector_cosine_ops)
-- WITH (lists = 100);

-- Transcript segment content embedding index (cosine similarity)
-- CREATE INDEX IF NOT EXISTS idx_segments_content_embedding
-- ON transcript_segments USING ivfflat (content_embedding vector_cosine_ops)
-- WITH (lists = 100);

-- Step 3: Verify
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
