from fastapi import APIRouter, HTTPException
import os
import google.generativeai as genai
from dotenv import load_dotenv
from pydantic import BaseModel
from database import SessionLocal

# Import retrieval tools
try:
    from retrieval_router import (
        hybrid_rrf_search, 
        rerank_hybrid_results, 
        collection, 
        embedding_model, 
        chunks_cache, 
        reranker_model
    )
except ImportError as e:
    print(f"DEBUG: Failed to import retrieval tools: {e}")

router = APIRouter()
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class ChatMessage(BaseModel):
    role: str
    content: str

class RAGChatRequest(BaseModel):
    query: str
    history: list[ChatMessage] = []

@router.post("/api/v1/chat", tags=["Generative AI & RAG"])
async def generate_rag_response(payload: RAGChatRequest):
    user_query = payload.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # DEFENSIVE CHECK: Verify retrieval components are initialized.
    # This prevents the 'NoneType' attribute error.
    missing = [name for name, val in [
        ("collection", collection), 
        ("embedding_model", embedding_model), 
        ("reranker_model", reranker_model)
    ] if val is None]
    
    if missing:
        raise HTTPException(status_code=500, detail=f"Retrieval engine not initialized. Missing components: {', '.join(missing)}")

    session = SessionLocal()
    try:
        # Perform retrieval
        hybrid_cands = hybrid_rrf_search(user_query, collection, chunks_cache, embedding_model, top_k=5)
        top_results = rerank_hybrid_results(user_query, [dict(i) for i in hybrid_cands], reranker_model, top_k=3)

        # Assemble context
        context_texts = [f"[Source {idx+1}: {res.get('metadata', {}).get('document_name', 'Unknown')}]\n{res.get('text', '')}" for idx, res in enumerate(top_results)]
        context_block = "\n\n".join(context_texts)
        citations = list(set([res.get("metadata", {}).get("document_name", "Unknown") for res in top_results]))

        # Generate response
        model = genai.GenerativeModel('gemini-1.5-flash')
        system_prompt = "You are an enterprise AI assistant. Answer strictly using the Context provided below. If the answer is not in the Context, say 'I do not have enough information to answer that.' Always cite your sources using the [Source X] labels."
        
        response = model.generate_content(f"{system_prompt}\n\nContext:\n{context_block}\n\nQuestion: {user_query}")
        
        return {
            "answer": response.text,
            "citations": citations,
            "retrieved_context": top_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG Integration Error: {str(e)}")
    finally:
        session.close()