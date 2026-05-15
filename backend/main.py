import os
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import faiss
import numpy as np
from pypdf import PdfReader

load_dotenv()

# Initialize OpenAI client
# Ensure OPENAI_API_KEY is set in your .env file
client = OpenAI()

app = FastAPI(title="Gold Standard RAG API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for documents and vector index
documents = []
index = None

class QueryRequest(BaseModel):
    query: str

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    global index, documents
    
    try:
        reader = PdfReader(file.file)
        text_chunks = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                # Simple chunking: 1000 chars with 200 overlap
                chunks = [text[i:i+1000] for i in range(0, len(text), 800)]
                for chunk in chunks:
                    text_chunks.append({"text": chunk, "page": i}) # 0-indexed for frontend compatibility
        
        if not text_chunks:
            raise HTTPException(status_code=400, detail="Could not extract text from PDF.")

        # Get embeddings via OpenAI SDK
        texts = [c["text"] for c in text_chunks]
        # Batch size limit for embeddings is large, but let's be safe
        response = client.embeddings.create(input=texts, model="text-embedding-3-small")
        embeddings = np.array([d.embedding for d in response.data]).astype('float32')

        # Initialize or add to FAISS index
        if index is None:
            index = faiss.IndexFlatL2(embeddings.shape[1])
        
        index.add(embeddings)
        documents.extend(text_chunks)
        
        return {"message": f"Successfully indexed {file.filename}", "chunks": len(text_chunks)}
    
    except Exception as e:
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/verify")
async def verify_query(request: QueryRequest):
    global index, documents
    
    if index is None:
        raise HTTPException(status_code=400, detail="No documents indexed yet. Please upload a PDF.")

    try:
        # 1. Embed the query
        query_response = client.embeddings.create(input=request.query, model="text-embedding-3-small")
        query_embed = np.array([query_response.data[0].embedding]).astype('float32')
        
        # 2. Search FAISS index (top 4 chunks)
        k = 4
        D, I = index.search(query_embed, k=min(k, len(documents)))
        
        relevant_docs = [documents[i] for i in I[0]]
        context = "\n\n".join([f"--- Source (Page {d['page'] + 1}) ---\n{d['text']}" for d in relevant_docs])

        # 3. Generate verification answer with GPT-4o
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": (
                        "You are a highly sensitive document verification assistant. "
                        "Use the provided context to verify information accurately. "
                        "If the answer is not in the context, say you cannot verify it. "
                        "Be precise, professional, and cite the page numbers used."
                    )
                },
                {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {request.query}"}
            ],
            temperature=0
        )

        answer = completion.choices[0].message.content
        
        # Format sources for frontend
        sources = [{"metadata": {"page": d["page"]}} for d in relevant_docs]
            
        return {
            "answer": answer,
            "sources": sources
        }
        
    except Exception as e:
        print(f"Verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "vector_store_initialized": index is not None}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
