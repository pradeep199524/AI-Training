import os
import re
import json
import numpy as np
import chromadb
import traceback
import matplotlib.pyplot as plt
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, joinedload
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
from models import Document, Page, Paragraph, CleanedCsvRecord

# --- PATH & ENVIRONMENT SETUP ---
load_dotenv()
SCRIPT_DIR = Path(__file__).resolve().parent

# FORCE PATH: Ensure vector_db is strictly created inside the 'data-engineering' directory
if SCRIPT_DIR.name in ["data_engineering", "data-engineering", "backend_service"]:
    DB_PATH = SCRIPT_DIR.parent / "data-engineering" / "vector_db"
else:
    DB_PATH = SCRIPT_DIR / "data-engineering" / "vector_db"

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("CRITICAL: DATABASE_URL not found in configuration.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# --- MODEL LOADING ---
SHARED_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name in ["data_engineering", "backend_service"] else SCRIPT_DIR
MODELS_DIR = SHARED_ROOT / "local_models"

print(f"📦 Initializing Models from shared directory: {MODELS_DIR}")

local_bi_path = MODELS_DIR / "all-MiniLM-L6-v2"
local_cross_path = MODELS_DIR / "ms-marco-MiniLM-L-6-v2"

embedding_model = SentenceTransformer(str(local_bi_path)) if local_bi_path.is_dir() else SentenceTransformer('all-MiniLM-L6-v2')
reranker_model = CrossEncoder(str(local_cross_path)) if local_cross_path.is_dir() else CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')


# --- NEW: ID EXTRACTION FUNCTION ---
def extract_employee_id(query_str):
    """Dynamically finds any 4+ digit number in the query."""
    match = re.search(r'(\d{4,})', query_str)
    return match.group(1) if match else None


# --- 1. ADVANCED QUERY INTELLIGENCE (NORMALIZATION, ROUTING & EXPANSION) ---

DOMAIN_DICTIONARY = {
    "prod": "production", 
    "integration": "integration system", 
    "pipeline": "data pipeline diagnostics", 
    "err": "error log",
    "dev": "development",
    "db": "database",
    "config": "configuration",
    "auth": "authentication"
}

STOP_WORDS = {"what", "is", "the", "how", "to", "find", "where", "can", "i", "a", "an", "of", "and", "in", "at", "on"}

def get_available_sources(session):
    docs = session.query(Document.filename).all()
    csvs = session.query(CleanedCsvRecord.source_csv).all()
    return [d[0] for d in docs] + [c[0] for c in csvs]

def get_source_filter(query_str: str, session, embed_model, threshold=0.35) -> str:
    available_sources = get_available_sources(session)
    if not available_sources:
        return None

    source_phrases = [re.sub(r'[._-]', ' ', src.lower()) for src in available_sources]
    source_embeddings = embed_model.encode(source_phrases)
    query_embedding = embed_model.encode([query_str.lower()])[0]

    best_score = -1
    best_source = None

    for idx, src_emb in enumerate(source_embeddings):
        dot_product = np.dot(query_embedding, src_emb)
        norm_q = np.linalg.norm(query_embedding)
        norm_s = np.linalg.norm(src_emb)
        similarity = dot_product / (norm_q * norm_s) if (norm_q * norm_s) > 0 else 0
        
        if similarity > best_score:
            best_score = similarity
            best_source = available_sources[idx]

    if best_score >= threshold:
        print(f"🎯 Query Intelligence routed query to: {best_source} (Confidence: {best_score:.2f})")
        return best_source
        
    return None

def optimize_query(query_str: str) -> str:
    cleaned = re.sub(r'[^\w\s-]', '', query_str.lower().strip())
    tokens = [word for word in cleaned.split() if word not in STOP_WORDS]
    normalized_tokens = [DOMAIN_DICTIONARY.get(word, word) for word in tokens]
    return " ".join(normalized_tokens)

def expand_query_with_llm(user_query: str) -> str:
    normalized = optimize_query(user_query)
    if "error" in normalized or "log" in normalized:
        return f"{normalized} stacktrace exception warning fault debugging latency"
    if "production" in normalized or "pipeline" in normalized:
        return f"{normalized} deployment orchestrator cluster stream telemetry ingest"
    return f"{normalized} configuration architecture deployment interface specs"

# --- 2. STRUCTURE-AWARE CLEAN CHUNKING ---
def generate_structure_aware_chunks(session):
    chunks = []
    paragraphs = session.query(Paragraph).options(
        joinedload(Paragraph.page).joinedload(Page.document)
    ).order_by(Paragraph.page_id, Paragraph.paragraph_index).all()
    
    for p in paragraphs:
        text_content = p.text_content.strip()
        if not text_content: continue
        doc_name = p.page.document.filename if (p.page and p.page.document) else "Unknown"
        page_num = p.page.page_number if p.page else 0

        chunks.append({
            "text": text_content, 
            # FIXED: Changed "page_number" to "page" for UI compatibility
            "metadata": {"document_name": doc_name, "page": page_num}
        })
    return chunks

def generate_csv_aware_chunks(session):
    chunks = []
    records = session.query(CleanedCsvRecord).all()
    
    def flatten_json(y):
        out = {}
        def flatten(x, name=''):
            if type(x) is dict:
                for a in x: flatten(x[a], name + a + '_')
            elif type(x) is list:
                for i, a in enumerate(x): flatten(a, name + str(i) + '_')
            else: out[name[:-1]] = x
        flatten(y)
        return out

    for record in records:
        try:
            flat_data = flatten_json(record.row_data)
            text_content = f"CSV Record from {record.source_csv}: " + ", ".join([f"{k}: {v}" for k, v in flat_data.items()])
            emp_id = str(flat_data.get("EmployeeID", ""))
            chunks.append({
                "text": text_content,
                "metadata": {
                    "document_name": record.source_csv,
                    # FIXED: Changed "page_number" to "page" for UI compatibility
                    "page": 0,
                    "employee_id": emp_id,
                }
            })
        except Exception as e:
            continue
    return chunks

# --- 3. PERSISTENT VECTOR STORE ---
def build_persistent_index(chunks, model):
    chroma_client = chromadb.PersistentClient(path=str(DB_PATH))
    collection = chroma_client.get_or_create_collection(name="pdf_documents", metadata={"hnsw:space": "cosine"})
    
    if len(chunks) > 0:
        texts = [c["text"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]
        ids = [f"{c['metadata']['document_name']}_{i}" for i, c in enumerate(chunks)]
        embeddings = model.encode(texts).tolist()
        collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        print(f"✅ ChromaDB freshly indexed with {len(chunks)} combined pipeline segments.")
    return collection

def normalize_metadata_filter(metadata_filter):
    if not metadata_filter or "$and" in metadata_filter or "$or" in metadata_filter:
        return metadata_filter
    if len(metadata_filter) > 1:
        return {"$and": [{k: v} for k, v in metadata_filter.items()]}
    return metadata_filter

# --- 4. RETRIEVAL & HYBRID RERANKING ---
def semantic_search(query_str, collection, model, top_k=3, metadata_filter=None):
    filter_to_use = normalize_metadata_filter(metadata_filter)
    res = collection.query(
        query_embeddings=model.encode([query_str]).tolist(), 
        n_results=top_k,
        where=filter_to_use 
    )
    if not res['documents'] or not res['documents'][0]: return []
    return [{"text": res['documents'][0][i], "score": float(1.0 - res['distances'][0][i]), "metadata": res['metadatas'][0][i]} for i in range(len(res['documents'][0]))]

def sparse_keyword_search(query_str, chunks, top_k=3, source_filter=None, emp_id_filter=None):
    filtered_chunks = [
        c for c in chunks 
        if (source_filter is None or c["metadata"].get("document_name") == source_filter) and
           (emp_id_filter is None or str(c["metadata"].get("employee_id", "")) == str(emp_id_filter))
    ]
    if not filtered_chunks: return []
    bm25 = BM25Okapi([c["text"].lower().split() for c in filtered_chunks])
    scores = bm25.get_scores(query_str.lower().split())
    ranked_indices = np.argsort(scores)[::-1][:top_k]
    results = []
    for idx in ranked_indices:
        if scores[idx] > 0:
            results.append({
                "text": filtered_chunks[idx]["text"],
                "score": float(scores[idx]),
                "metadata": filtered_chunks[idx]["metadata"] 
            })
    return results
    
def hybrid_rrf_search(query_str, collection, chunks, model, top_k=3, k=60, metadata_filter=None):
    dense = semantic_search(query_str, collection, model, top_k=min(len(chunks), 10), metadata_filter=metadata_filter)
    
    source_name = None
    emp_id = None
    if metadata_filter:
        conditions = metadata_filter.get("$and", [metadata_filter])
        for cond in conditions:
            if "document_name" in cond: source_name = cond["document_name"]
            if "employee_id" in cond: emp_id = cond["employee_id"]

    sparse = sparse_keyword_search(query_str, chunks, top_k=min(len(chunks), 10), 
                                   source_filter=source_name, emp_id_filter=emp_id)
    
    scores = {}
    doc_map = {}
    for d in dense + sparse:
        doc_map[d["text"]] = d.get("metadata", {})
        
    for r, d in enumerate(dense, 1): scores[d["text"]] = scores.get(d["text"], 0.0) + (1.0 / (k + r))
    for r, d in enumerate(sparse, 1): scores[d["text"]] = scores.get(d["text"], 0.0) + (1.0 / (k + r))
        
    sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [{"text": t, "score": s, "metadata": doc_map[t]} for t, s in sorted_docs]


# --- UPGRADED RERANKER: HARD BOOST FOR ID ---
def rerank_hybrid_results(query_str, candidates, reranker, top_k=3, target_emp_id=None):
    if not candidates: return []
    
    for c in candidates:
        meta_id = str(c["metadata"].get("employee_id", ""))
        if target_emp_id and meta_id == str(target_emp_id):
            c["rerank_score"] = 999.0
        else:
            c["rerank_score"] = 0.0

    if not any(c.get("rerank_score") == 999.0 for c in candidates):
        scores = reranker.predict([[query_str, c["text"]] for c in candidates])
        for i, s in enumerate(scores): 
            candidates[i]["rerank_score"] = float(s)
            
    return sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)[:top_k]


# --- 5. ENTERPRISE OFFLINE EVALUATION BENCHMARK METRICS ---
def run_offline_evaluation_benchmark(chunks_cache, collection):
    golden_dataset = [
        {"query": "production pipeline integration error logs", "expected_document": "pipeline_diagnostics.pdf"},
        {"query": "Show me the information regarding the individual with EmployeeID 1005.", "expected_document": "employee_dataset.csv"}
    ]
    
    print("\n📊 STARTING OFFLINE RETRIEVAL EVALUATION PIPELINE...")
    total_queries = len(golden_dataset)
    if total_queries == 0: return

    strategies = ["Dense Vector Search", "Sparse Keyword", "Hybrid + Reranking"]
    hit_counts = {s: 0 for s in strategies}
    mrr_reciprocals = {s: 0 for s in strategies}
    session = SessionLocal()

    for item in golden_dataset:
        raw_q = item["query"]
        target_doc = item["expected_document"]
        
        expanded_q = expand_query_with_llm(raw_q)
        dynamic_filter = get_source_filter(raw_q, session, embedding_model)
        emp_id = extract_employee_id(raw_q)
        
        # Build Filter Map
        meta_filter = {}
        if dynamic_filter: meta_filter["document_name"] = dynamic_filter
        if emp_id: meta_filter["employee_id"] = emp_id

        results_map = {
            "Dense Vector Search": semantic_search(expanded_q, collection, embedding_model, top_k=5, metadata_filter=meta_filter if meta_filter else None),
            "Sparse Keyword": sparse_keyword_search(expanded_q, chunks_cache, top_k=5, source_filter=dynamic_filter, emp_id_filter=emp_id),
            "Hybrid + Reranking": rerank_hybrid_results(
                expanded_q, 
                [dict(x) for x in hybrid_rrf_search(expanded_q, collection, chunks_cache, embedding_model, top_k=10, metadata_filter=meta_filter if meta_filter else None)],
                reranker_model, 
                top_k=5,
                target_emp_id=emp_id
            )
        }
        
        for strat, results in results_map.items():
            hit_detected = False
            for rank, item_res in enumerate(results, start=1):
                doc_found = item_res.get("metadata", {}).get("document_name", "")
                if doc_found == target_doc:
                    if not hit_detected:
                        hit_counts[strat] += 1
                        hit_detected = True
                    mrr_reciprocals[strat] += (1.0 / rank)
                    break

    session.close()

    print("\n================== BENCHMARK METRIC MATRIX ==================")
    for s in strategies:
        final_hr = (hit_counts[s] / total_queries) * 100
        final_mrr = mrr_reciprocals[s] / total_queries
        print(f"🔹 Strategy: {s:<25} | Hit Rate @5: {final_hr:>5.1f}% | MRR: {final_mrr:.3f}")
    print("=============================================================\n")

# --- 🚀 RUN LOOP SYSTEM ---
def main():
    session = SessionLocal()
    pdf_chunks = generate_structure_aware_chunks(session)
    csv_chunks = generate_csv_aware_chunks(session)
    combined_chunks = pdf_chunks + csv_chunks
    session.close()
    
    collection = build_persistent_index(combined_chunks, embedding_model)
    print(f"🚀 Vector pipeline execution test successfully configured with {len(combined_chunks)} total entries.")
    run_offline_evaluation_benchmark(combined_chunks, collection)

if __name__ == "__main__":
    main()