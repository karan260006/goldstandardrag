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
client = OpenAI()

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOTE: These will be lost between requests in Vercel's serverless environment
documents = []
index = None

class QueryRequest(BaseModel):
    query: str

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    global index, documents
    try:
        reader = PdfReader(file.file)
        text_chunks = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                chunks = [text[i:i+1000] for i in range(0, len(text), 800)]
                for chunk in chunks:
                    text_chunks.append({"text": chunk, "page": i})
        
        if not text_chunks:
            raise HTTPException(status_code=400, detail="Could not extract text from PDF.")

        texts = [c["text"] for c in text_chunks]
        response = client.embeddings.create(input=texts, model="text-embedding-3-small")
        embeddings = np.array([d.embedding for d in response.data]).astype('float32')

        if index is None:
            index = faiss.IndexFlatL2(embeddings.shape[1])
        
        index.add(embeddings)
        documents.extend(text_chunks)
        
        return {"message": f"Successfully indexed {file.filename}", "chunks": len(text_chunks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/verify")
async def verify_query(request: QueryRequest):
    global index, documents
    if index is None:
        raise HTTPException(status_code=400, detail="No documents indexed. Please upload a PDF.")

    try:
        query_response = client.embeddings.create(input=request.query, model="text-embedding-3-small")
        query_embed = np.array([query_response.data[0].embedding]).astype('float32')
        
        k = 4
        D, I = index.search(query_embed, k=min(k, len(documents)))
        relevant_docs = [documents[i] for i in I[0]]
        context = "\n\n".join([f"--- Source (Page {d['page'] + 1}) ---\n{d['text']}" for d in relevant_docs])

        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a verification assistant. Use the context to verify. Cite page numbers."},
                {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {request.query}"}
            ],
            temperature=0
        )
        return {
            "answer": completion.choices[0].message.content,
            "sources": [{"metadata": {"page": d["page"]}} for d in relevant_docs]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health():
    return {"status": "healthy"}
