import os
import re
import traceback
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
import chromadb

# Internal project imports
from database import SessionLocal
from generate_embeddings import (
    generate_structure_aware_chunks,
    optimize_query,
    expand_query_with_llm,
    semantic_search,
    sparse_keyword_search,
    hybrid_rrf_search,
    rerank_hybrid_results,
    embedding_model,
    reranker_model,
    get_source_filter,
    extract_employee_id  # <--- IMPORTED OUR NEW FUNCTION
)

router = APIRouter()

# ==========================================================================
# RETRIEVAL CONFIGURATION & STATE
# ==========================================================================
RETRIEVAL_CONFIG = {
    "DENSE_SCORE_THRESHOLD": 0.25,
    "SPARSE_SCORE_THRESHOLD": 0.1,
    "RERANK_SCORE_THRESHOLD": -4.0,
    "MAX_RRF_CANDIDATES": 20,
    "DISPLAY_LIMIT": 2,
    "SEARCH_TOP_K": 5,
    "ROUTING_THRESHOLD": 0.25  
}

chunks_cache = []
collection = None

def initialize_retrieval_system(base_dir: str):
    global chunks_cache, collection
    
    try:
        print(f"⚡ Module 4 retrieval systems detected. Initializing engine context...")
        base_path = Path(base_dir).resolve()
        target_eng_dir = base_path / "data-engineering"
        
        if not target_eng_dir.exists():
            target_eng_dir = base_path.parent / "data-engineering"
            
        absolute_db_path = target_eng_dir / "vector_db"
        
        if not absolute_db_path.exists():
            print(f"❌ ERROR: Cannot locate vector_db folder at {absolute_db_path}")
            return
        
        chroma_client = chromadb.PersistentClient(path=str(absolute_db_path))
        collection = chroma_client.get_or_create_collection(
            name="pdf_documents", 
            metadata={"hnsw:space": "cosine"}
        )
        
        startup_session = SessionLocal()
        chunks_cache = generate_structure_aware_chunks(startup_session)
        
        try:
            csv_records = startup_session.execute(text("SELECT source_csv, row_data FROM cleaned_csv_records;")).fetchall()
            loaded_count = 0
            for r in csv_records:
                if r[1]:
                    items = [f"{k}: {v}" for k, v in r[1].items()]
                    chunks_cache.append({
                        "text": f"CSV Record from {r[0]} -> " + ", ".join(items),
                        "metadata": {"document_name": r[0], "page_number": 1}
                    })
                    loaded_count += 1
            print(f"📊 SUCCESS: Loaded {loaded_count} CSV records.")
        except Exception as csv_err:
            print(f"❌ CRITICAL: Failed to load CSV records: {str(csv_err)}")
            
        startup_session.close()
        print(f"✅ SUCCESS: Retrieval engine contexts fully established.")
        
    except Exception as e:
        print(f"⚠️ Module 4 initialization failed:\n{traceback.format_exc()}")
        raise e

# ==========================================================================
# API ENDPOINT
# ==========================================================================
class Module4SearchQueryRequest(BaseModel):
    query: str

@router.post("/api/v1/retrieve", tags=["Data Engine Lookups"])
async def retrieve_and_evaluate_strategies(payload: Module4SearchQueryRequest):
    global chunks_cache, collection
    
    cfg = RETRIEVAL_CONFIG
    user_query = payload.query.strip()
    
    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if not chunks_cache or collection is None:
        raise HTTPException(status_code=503, detail="System not initialized.")

    session = SessionLocal()
    normalized = optimize_query(user_query)
    expanded = expand_query_with_llm(normalized)

    try:
        # ==================================================================
        # 🔥 ANALYTICAL ROUTER (FIX FOR AGGREGATION QUERIES)
        # ==================================================================
        analytical_keywords = ["how many", "count", "total", "breakdown"]
        if any(kw in user_query.lower() for kw in analytical_keywords):
            dept_counts = {}
            for chunk in chunks_cache:
                txt = chunk.get("text", "")
                if "department:" in txt.lower():
                    try:
                        dept = txt.split("Department:")[1].split(",")[0].strip()
                        dept_counts[dept] = dept_counts.get(dept, 0) + 1
                    except: continue
            
            res_text = f"Analytical Summary: " + ", ".join([f"{k}: {v}" for k, v in dept_counts.items()])
            agg_result = [{
                "text": res_text, 
                "score": 1.0, 
                "document_name": "Aggregator", 
                "page_number": 1,
                "metadata": {"document_name": "Aggregator", "page_number": 1}
            }]
            
            return {
                "input_query": user_query,
                "normalized_query": normalized,
                "expanded_query": expanded,
                "dense_results": agg_result,
                "sparse_results": agg_result,
                "hybrid_results": agg_result,
                "charts_data": [{"strategy": "Analytical Aggregator", "accuracy": 100.0}]
            }

        # ==================================================================
        # STANDARD RAG PIPELINE (FIXED FILTER LOGIC)
        # ==================================================================
        dynamic_filter = get_source_filter(user_query, session, embedding_model, cfg["ROUTING_THRESHOLD"])
        
        # 0. Build the Metadata Filter
        filter_conditions = []
        
        if dynamic_filter:
            filter_conditions.append({"document_name": dynamic_filter})
            
        emp_id = extract_employee_id(user_query)
        if emp_id:
            filter_conditions.append({"employee_id": str(emp_id)})

        # Apply ChromaDB syntax rules
        if len(filter_conditions) > 1:
            meta_filter = {"$and": filter_conditions}
        elif len(filter_conditions) == 1:
            meta_filter = filter_conditions[0]
        else:
            meta_filter = None

        # 1. DENSE
        dense_matches = semantic_search(expanded, collection, embedding_model, top_k=cfg["SEARCH_TOP_K"], metadata_filter=meta_filter)
        approach_dense = dense_matches[:cfg["DISPLAY_LIMIT"]]

        # 2. SPARSE (Added source & id filters)
        sparse_matches = sparse_keyword_search(normalized, chunks_cache, top_k=cfg["SEARCH_TOP_K"], source_filter=dynamic_filter, emp_id_filter=emp_id)
        approach_sparse = sparse_matches[:cfg["DISPLAY_LIMIT"]]

        # 3. HYBRID (Added meta_filter and target_emp_id)
        hybrid_cands = hybrid_rrf_search(normalized, collection, chunks_cache, embedding_model, top_k=cfg["MAX_RRF_CANDIDATES"], metadata_filter=meta_filter)
        approach_hybrid = rerank_hybrid_results(expanded, [dict(i) for i in hybrid_cands], reranker_model, top_k=cfg["DISPLAY_LIMIT"], target_emp_id=emp_id)

        # --- FIX: FLATTEN METADATA FOR REACT UI COMPATIBILITY ---
        for result_list in [approach_dense, approach_sparse, approach_hybrid]:
            for item in result_list:
                if "metadata" in item:
                    item["document_name"] = item["metadata"].get("document_name", "Unknown")
                    item["page_number"] = item["metadata"].get("page_number", 1)

        # Evaluation Analytics
        def get_acc(res, q): return 100.0 if res and any(t in str(res[0]).lower() for t in q.lower().split() if len(t)>2) else 0.0
        
        return {
            "input_query": user_query,
            "normalized_query": normalized,
            "expanded_query": expanded,
            "dense_results": approach_dense,
            "sparse_results": approach_sparse,
            "hybrid_results": approach_hybrid,
            "charts_data": [
                {"strategy": "Sparse Keyword", "accuracy": get_acc(approach_sparse, user_query)},
                {"strategy": "Dense Vector", "accuracy": get_acc(approach_dense, user_query)},
                {"strategy": "Hybrid", "accuracy": get_acc(approach_hybrid, user_query)}
            ]
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        session.close()