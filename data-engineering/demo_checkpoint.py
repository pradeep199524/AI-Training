import os
import chromadb
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sentence_transformers import SentenceTransformer, CrossEncoder
from dotenv import load_dotenv
from generate_embeddings import optimize_query, hybrid_rrf_search, rerank_hybrid_results, generate_structure_aware_chunks, semantic_search

load_dotenv()
local_bi_path = "./data-engineering/local_models/all-MiniLM-L6-v2"
local_cross_path = "./data-engineering/local_models/ms-marco-MiniLM-L-6-v2"

print("🔄 Initializing Offline Demo Engine...")
embedding_model = SentenceTransformer(local_bi_path)
reranker_model = CrossEncoder(local_cross_path)
chroma_client = chromadb.PersistentClient(path="./data-engineering/vector_db")
collection = chroma_client.get_collection(name="pdf_documents")

# Reconstruct chunks for sparse mapping reference
engine = create_engine(os.getenv("DATABASE_URL"))
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()
chunks = generate_structure_aware_chunks(session)
session.close()

def run_live_demo(user_query):
    print("\n" + "="*80)
    print(f"🔍 LIVE DEMO FOR QUERY: '{user_query}'")
    print("="*80)
    
    # 1. Search WITHOUT Query Intelligence (Raw Input)
    print("\n❌ APPROACH A: Dense Search WITHOUT Query Intelligence (Raw)")
    raw_dense = semantic_search(user_query, collection, embedding_model, top_k=2)
    for r, match in enumerate(raw_dense, 1):
        print(f"  Rank [{r}] | Score: {match['score']:.4f} | Source: {match['metadata']['document_name']} (Page {match['metadata']['page_number']})")
        print(f"  Excerpt: {match['text'][:90]}...\n")

    # 2. Search WITH Query Intelligence + Hybrid + Reranking
    print("-" * 80)
    optimized = optimize_query(user_query)
    print(f"🧠 APPROACH B: Advanced Pipeline (Query Intelligence -> Hybrid RRF -> Reranker)")
    print(f"✨ Expanded Query: '{optimized}'")
    print("-" * 80)
    
    hybrid_candidates = hybrid_rrf_search(optimized, collection, chunks, embedding_model, top_k=len(chunks))
    final_results = rerank_hybrid_results(optimized, hybrid_candidates, reranker_model, top_k=2)
    
    for r, match in enumerate(final_results, 1):
        print(f"  🥇 Rank [{r}] | Rerank Confidence: {match['rerank_score']:.4f}")
        print(f"  📄 Source Link: File:///{match['metadata']['document_name']}#page={match['metadata']['page_number']}")
        print(f"  📝 Retrieved Chunk: {match['text'][:180]}...\n")

if __name__ == "__main__":
    # Test question matching shorthand developer terms
    run_live_demo("prod pipeline err")