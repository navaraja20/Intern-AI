"""
RAG (Retrieval-Augmented Generation) Service.
Manages embeddings and semantic retrieval from ChromaDB.

Pipeline:
  1. Chunk text into overlapping segments
  2. Generate embeddings (sentence-transformers: all-MiniLM-L6-v2)
  3. Store in ChromaDB with metadata
  4. Retrieve top-k relevant chunks for a given query
"""

import hashlib
from typing import List, Optional
from functools import lru_cache

from fastembed import TextEmbedding
from config import settings
from database import get_chroma_collection


# ── Embedding Model (lazy singleton) ─────────────────────────────────────────

@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    "Load once, reuse everywhere. ONNX-based, no PyTorch needed."
    return TextEmbedding(model_name=settings.EMBEDDING_MODEL)


def embed(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts."""
    model = get_embedding_model()
    return [e.tolist() for e in model.embed(texts)]


def embed_single(text: str) -> List[float]:
    return embed([text])[0]


# ── Text Chunking ─────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: int = None,
    overlap: int = None,
) -> List[str]:
    """
    Split text into overlapping character-based chunks.
    Respects paragraph boundaries where possible.
    """
    chunk_size = chunk_size or settings.EMBEDDING_CHUNK_SIZE
    overlap    = overlap    or settings.EMBEDDING_CHUNK_OVERLAP

    # Split on double newlines first (paragraph-aware)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) <= chunk_size:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            # Para itself might be too long → split by chars
            if len(para) > chunk_size:
                for i in range(0, len(para), chunk_size - overlap):
                    sub = para[i : i + chunk_size]
                    if sub.strip():
                        chunks.append(sub.strip())
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


def _doc_id(user_id: int, source: str, chunk_index: int, content: str) -> str:
    """Deterministic ID to prevent duplicate insertions."""
    h = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"u{user_id}_{source}_{chunk_index}_{h}"


# ── Indexing ──────────────────────────────────────────────────────────────────

def index_resume(user_id: int, resume_text: str) -> int:
    """
    Chunk and embed the user's resume into ChromaDB.
    Deletes old resume chunks for this user before re-indexing.
    Returns number of chunks indexed.
    """
    collection = get_chroma_collection(settings.CHROMA_COLLECTION_RESUME)

    # Delete existing chunks for this user
    try:
        existing = collection.get(where={"user_id": user_id})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    chunks = chunk_text(resume_text)
    if not chunks:
        return 0

    embeddings = embed(chunks)
    ids = [_doc_id(user_id, "resume", i, c) for i, c in enumerate(chunks)]
    metadatas = [{"user_id": user_id, "source": "resume", "chunk_index": i}
                 for i in range(len(chunks))]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )
    return len(chunks)


def index_linkedin(user_id: int, about: str, experiences_text: str, skills_text: str) -> int:
    """Embed LinkedIn profile content."""
    collection = get_chroma_collection(settings.CHROMA_COLLECTION_EXPERIENCES)

    # Remove old
    try:
        existing = collection.get(
            where={"$and": [{"user_id": user_id}, {"source": "linkedin"}]}
        )
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    combined = "\n\n".join(filter(None, [about, experiences_text, skills_text]))
    if not combined.strip():
        return 0

    chunks = chunk_text(combined)
    embeddings = embed(chunks)
    ids = [_doc_id(user_id, "linkedin", i, c) for i, c in enumerate(chunks)]
    metadatas = [{"user_id": user_id, "source": "linkedin", "chunk_index": i}
                 for i in range(len(chunks))]

    collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
    return len(chunks)


def index_github_repos(user_id: int, repos: list[dict]) -> int:
    """Embed GitHub repos (name + description + README)."""
    collection = get_chroma_collection(settings.CHROMA_COLLECTION_GITHUB)

    try:
        existing = collection.get(where={"user_id": user_id})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    all_chunks, all_embeddings, all_ids, all_meta = [], [], [], []
    chunk_idx = 0

    for repo in repos:
        repo_text = _repo_to_text(repo)
        chunks = chunk_text(repo_text, chunk_size=600)
        for chunk in chunks:
            all_chunks.append(chunk)
            all_ids.append(_doc_id(user_id, f"github_{repo['repo_name']}", chunk_idx, chunk))
            all_meta.append({
                "user_id": user_id,
                "source": "github",
                "repo_name": repo["repo_name"],
                "chunk_index": chunk_idx,
            })
            chunk_idx += 1

    if not all_chunks:
        return 0

    all_embeddings = embed(all_chunks)
    collection.add(
        ids=all_ids,
        embeddings=all_embeddings,
        documents=all_chunks,
        metadatas=all_meta,
    )
    return len(all_chunks)


def _repo_to_text(repo: dict) -> str:
    parts = [f"Repository: {repo.get('repo_name', '')}"]
    if repo.get("description"):
        parts.append(f"Description: {repo['description']}")
    if repo.get("language"):
        parts.append(f"Primary language: {repo['language']}")
    if repo.get("topics"):
        parts.append(f"Topics: {', '.join(repo['topics'])}")
    if repo.get("readme_text"):
        parts.append(f"README:\n{repo['readme_text'][:1000]}")
    return "\n".join(parts)


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve_for_jd(
    user_id: int,
    job_description: str,
    top_k: int = None,
) -> dict:
    """
    Main RAG retrieval: query all three collections for relevant context.
    Returns a dict with top chunks from each source + merged context string.
    """
    top_k = top_k or settings.RAG_TOP_K
    jd_embedding = embed_single(job_description)

    results = {"resume": [], "linkedin": [], "github": [], "context": ""}

    # Resume chunks
    try:
        resume_col = get_chroma_collection(settings.CHROMA_COLLECTION_RESUME)
        r = resume_col.query(
            query_embeddings=[jd_embedding],
            n_results=min(top_k, 10),
            where={"user_id": user_id},
        )
        results["resume"] = r["documents"][0] if r["documents"] else []
    except Exception:
        pass

    # LinkedIn chunks
    try:
        exp_col = get_chroma_collection(settings.CHROMA_COLLECTION_EXPERIENCES)
        r = exp_col.query(
            query_embeddings=[jd_embedding],
            n_results=min(top_k, 5),
            where={"$and": [{"user_id": user_id}, {"source": "linkedin"}]},
        )
        results["linkedin"] = r["documents"][0] if r["documents"] else []
    except Exception:
        pass

    # GitHub chunks
    try:
        gh_col = get_chroma_collection(settings.CHROMA_COLLECTION_GITHUB)
        r = gh_col.query(
            query_embeddings=[jd_embedding],
            n_results=min(top_k, 5),
            where={"user_id": user_id},
        )
        results["github"] = r["documents"][0] if r["documents"] else []
    except Exception:
        pass

    # Build merged context string for LLM injection
    context_parts = []
    if results["resume"]:
        context_parts.append("### Most Relevant Resume Sections:\n" +
                             "\n---\n".join(results["resume"][:3]))
    if results["linkedin"]:
        context_parts.append("### Relevant LinkedIn Experience:\n" +
                             "\n---\n".join(results["linkedin"][:2]))
    if results["github"]:
        context_parts.append("### Relevant GitHub Projects:\n" +
                             "\n---\n".join(results["github"][:2]))

    results["context"] = "\n\n".join(context_parts)
    return results


def compute_semantic_similarity(resume_text: str, jd_text: str) -> float:
    """
    Cosine similarity between full resume and JD embeddings.
    Returns 0.0 – 1.0.
    """
    from numpy import dot
    from numpy.linalg import norm

    r_emb = embed_single(resume_text[:3000])
    j_emb = embed_single(jd_text[:3000])

    similarity = dot(r_emb, j_emb) / (norm(r_emb) * norm(j_emb) + 1e-9)
    return float(max(0.0, min(1.0, similarity)))
