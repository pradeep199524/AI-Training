import os
import re
import numpy as np
import chromadb
import matplotlib.pyplot as plt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, joinedload
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
from models import Document, Page, Paragraph

# 1. Initialization and Database Connection
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("CRITICAL: DATABASE_URL not found in configuration.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# --- OFFLINE-FIRST MODEL LOADING WITH AUTO-DOWNLOAD FIX ---
local_bi_path = "./data-engineering/local_models/all-MiniLM-L6-v2"
local_cross_path = "./data-engineering/local_models/ms-marco-MiniLM-L-6-v2"

# Load or auto-download Bi-Encoder
if os.path.exists(local_bi_path):
    print(f"📦 Loading embedding model locally from: {local_bi_path}")
    embedding_model = SentenceTransformer(local_bi_path)
else:
    print("🌐 Downloading embedding model from Hugging Face...")
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    os.makedirs(local_bi_path, exist_ok=True)
    embedding_model.save(local_bi_path)

# Load or auto-download Cross-Encoder safely
if os.path.exists(local_cross_path):
    print(f"📦 Loading reranker model locally from: {local_cross_path}")
    reranker_model = CrossEncoder(local_cross_path)
else:
    print("🌐 Path not found. Pulling reranker sequentially from Hugging Face...")
    reranker_model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    os.makedirs(local_cross_path, exist_ok=True)
    reranker_model.save_pretrained(local_cross_path)
    print(f"✅ Cached reranker locally at: {local_cross_path}")


# --- QUERY INTELLIGENCE LAYER ---
def optimize_query(query_str):
    cleaned = query_str.lower().strip()
    cleaned = re.sub(r'[^\w\s-]', '', cleaned)
    synonym_map = {
        "prod": "production",
        "integration": "integration system",
        "pipeline": "data pipeline diagnostics",
        "err": "error log"
    }
    words = cleaned.split()
    return " ".join([synonym_map.get(w, w) for w in words])


# --- DATA EXTRACTION & COHERENT CHUNKING ---
def generate_structure_aware_chunks(session):
    chunks = []
    paragraphs = (
        session.query(Paragraph)
        .options(joinedload(Paragraph.page).joinedload(Page.document))
        .order_by(Paragraph.page_id, Paragraph.paragraph_index)
        .all()
    )
    current_chunk = []
    current_word_count = 0
    max_words_per_chunk = 150  
    
    for p in paragraphs:
        text = p.text_content.strip()
        if not text: continue
        words = text.split()
        current_chunk.append(text)
        current_word_count += len(words)
        
        if current_word_count >= max_words_per_chunk:
            chunks.append({
                "text": " ".join(current_chunk),
                "metadata": {
                    "document_name": p.page.document.filename if (p.page and p.page.document) else "Unknown",
                    "page_number": p.page.page_number if p.page else 0
                }
            })
            current_chunk = []
            current_word_count = 0
            
    if current_chunk:
        chunks.append({
            "text": " ".join(current_chunk),
            "metadata": {"document_name": "Remaining Summary Data", "page_number": 0}
        })
    return chunks


# --- PERSISTENT VECTOR STORE LAYERS ---
def build_persistent_index(chunks, model):
    db_path = "./data-engineering/vector_db"
    chroma_client = chromadb.PersistentClient(path=db_path)
    collection = chroma_client.get_or_create_collection(name="pdf_documents", metadata={"hnsw:space": "cosine"})
    
    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    ids = [f"chunk_{i}" for i in range(len(chunks))]
    
    embeddings = model.encode(texts, show_progress_bar=False).tolist()
    collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
    return collection


# --- SEARCH STRATEGY IMPLEMENTATIONS ---
def semantic_search(query_str, collection, model, top_k=3):
    query_vector = model.encode([query_str]).tolist()
    raw_results = collection.query(query_embeddings=query_vector, n_results=top_k)
    formatted_results = []
    if not raw_results or not raw_results['documents'] or len(raw_results['documents'][0]) == 0:
        return formatted_results
    for i in range(len(raw_results['documents'][0])):
        formatted_results.append({
            "text": raw_results['documents'][0][i],
            "score": float(1.0 - raw_results['distances'][0][i]),
            "metadata": raw_results['metadatas'][0][i]
        })
    return formatted_results

def sparse_keyword_search(query_str, chunks, top_k=3):
    tokenized_corpus = [c["text"].lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = query_str.lower().split()
    scores = bm25.get_scores(tokenized_query)
    ranked_indices = np.argsort(scores)[::-1][:top_k]
    
    results = []
    for idx in ranked_indices:
        results.append({
            "text": chunks[idx]["text"],
            "score": float(scores[idx]),
            "metadata": chunks[idx]["metadata"]
        })
    return results

def hybrid_rrf_search(query_str, collection, chunks, model, top_k=3, k=60):
    dense_res = semantic_search(query_str, collection, model, top_k=len(chunks))
    sparse_res = sparse_keyword_search(query_str, chunks, top_k=len(chunks))
    rrf_scores = {}
    doc_map = {}
    
    for rank, doc in enumerate(dense_res, 1):
        text = doc["text"]
        doc_map[text] = doc["metadata"]
        rrf_scores[text] = rrf_scores.get(text, 0.0) + (1.0 / (k + rank))
        
    for rank, doc in enumerate(sparse_res, 1):
        text = doc["text"]
        doc_map[text] = doc["metadata"]
        rrf_scores[text] = rrf_scores.get(text, 0.0) + (1.0 / (k + rank))
        
    sorted_docs = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    return [{"text": text, "score": score, "metadata": doc_map[text]} for text, score in sorted_docs]

def rerank_hybrid_results(query_str, hybrid_candidates, reranker, top_k=3):
    if not hybrid_candidates: return []
    pairs = [[query_str, doc["text"]] for doc in hybrid_candidates]
    rerank_scores = reranker.predict(pairs)
    for i, score in enumerate(rerank_scores):
        hybrid_candidates[i]["rerank_score"] = float(score)
    return sorted(hybrid_candidates, key=lambda x: x["rerank_score"], reverse=True)[:top_k]


# --- EVALUATION BENCHMARK IMPLEMENTATION ---
def run_evaluation_benchmark(collection, chunks):
    """
    Evaluates system accuracy across 5 distinct sample queries using Hit Rate @ 1.
    """
    # Ground-truth dataset pairing sample queries with expected source targets
    benchmark_dataset = [
        {"query": "Sample Business Report Company ABC Retail", "target_page": 3},
        {"query": "Department Performance Sales increased by 18", "target_page": 1},
        {"query": "prod integration err pipeline", "target_page": 3},
        {"query": "Finance improved payment processing", "target_page": 1},
        {"query": "Executive Summary This PDF is provided as sample input", "target_page": 3}
    ]
    
    strategies = {"Sparse (BM25)": 0, "Dense (Vector)": 0, "Hybrid + Reranker": 0}
    
    for item in benchmark_dataset:
        optimized = optimize_query(item["query"])
        target = item["target_page"]
        
        # Test Strategy 1: Sparse Search
        s_res = sparse_keyword_search(optimized, chunks, top_k=1)
        if s_res and s_res[0]["metadata"]["page_number"] == target:
            strategies["Sparse (BM25)"] += 1
            
        # Test Strategy 2: Dense Search
        d_res = semantic_search(optimized, collection, embedding_model, top_k=1)
        if d_res and d_res[0]["metadata"]["page_number"] == target:
            strategies["Dense (Vector)"] += 1
            
        # Test Strategy 3: Full Reranked Hybrid Search
        h_cand = hybrid_rrf_search(optimized, collection, chunks, embedding_model, top_k=len(chunks))
        r_res = rerank_hybrid_results(optimized, h_cand, reranker_model, top_k=1)
        if r_res and r_res[0]["metadata"]["page_number"] == target:
            strategies["Hybrid + Reranker"] += 1

    # Convert correct hits to accuracy percentages
    total_queries = len(benchmark_dataset)
    accuracy_results = {algo: (hits / total_queries) * 100 for algo, hits in strategies.items()}
    
    print("\n📈 Benchmark System Accuracy Results Summary:")
    for algo, accuracy in accuracy_results.items():
        print(f" - {algo}: {accuracy:.1f}% Accuracy")
        
    # Generate Matplotlib Comparison Plot
    plt.figure(figsize=(8, 5))
    colors = ['#E57373', '#64B5F6', '#81C784']
    plt.bar(accuracy_results.keys(), accuracy_results.values(), color=colors, edgecolor='grey', width=0.6)
    plt.title("Retrieval Strategy Accuracy Comparison (Hit Rate @ 1)", fontsize=14, fontweight='bold', pad=15)
    plt.xlabel("Search Method Engine Type", fontsize=11, labelpad=10)
    plt.ylabel("System Accuracy Percentage (%)", fontsize=11, labelpad=10)
    plt.ylim(0, 110)
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    
    # Save the output visualization directly to disk
    plot_path = "./data-engineering/retrieval_accuracy_comparison.png"
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    print(f"\n📊 Accuracy comparison graph exported successfully to: {plot_path}")


# --- MAIN PIPELINE EXECUTION ---
def main():
    session = SessionLocal()
    chunks = generate_structure_aware_chunks(session)
    session.close()
    if not chunks: return

    collection = build_persistent_index(chunks, embedding_model)
    
    # Run the comprehensive test evaluation step
    run_evaluation_benchmark(collection, chunks)

if __name__ == "__main__":
    main()