import os
import uuid
import logging
import json
from typing import Optional
from io import BytesIO

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from groq import Groq
from openai import OpenAI
import requests
import uvicorn

# ======================================================
# 🔑 SUAS CHAVES (inseridas diretamente)
# ======================================================
GROQ_API_KEY = "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"
OPENROUTER_API_KEY = "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"
HUGGINGFACE_TOKEN = "AQ.Ab8RN6K8BB0TzXystIIgio198sgSQTQG4XxrcPtPrGgJliEtrg"

# ======================================================
# CONFIGURAÇÕES
# ======================================================
GROQ_MODEL = "llama-3.3-70b-versatile"
OPENROUTER_MODEL = "meta-llama/llama-3.2-3b-instruct:free"
HF_MODEL = "meta-llama/Llama-3.2-3B-Instruct"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Lenior Chat - Multi-Provider")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Clientes ---
groq_client = Groq(api_key=GROQ_API_KEY)

openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Lenior Chat"
    }
)

# --- Sessões em memória ---
sessoes: dict = {}

# ======================================================
# MODELOS
# ======================================================
class ChatRequest(BaseModel):
    texto: str
    sessao_id: Optional[str] = None

class ChatResponse(BaseModel):
    resposta: str
    sessao_id: str

# ======================================================
# FUNÇÕES DE CHAMADA (FALLBACK)
# ======================================================

def chamar_groq(mensagens: list) -> str:
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=mensagens,
            temperature=0.7,
            max_tokens=1024
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq falhou: {str(e)}")
        raise Exception(f"Groq: {str(e)}")

def chamar_openrouter(mensagens: list) -> str:
    try:
        response = openrouter_client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=mensagens,
            temperature=0.7,
            max_tokens=1024
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenRouter falhou: {str(e)}")
        raise Exception(f"OpenRouter: {str(e)}")

def chamar_huggingface(mensagens: list) -> str:
    try:
        prompt = ""
        for msg in mensagens:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt += f"<|system|>\n{content}\n"
            elif role == "user":
                prompt += f"<|user|>\n{content}\n"
            elif role == "assistant":
                prompt += f"<|assistant|>\n{content}\n"
        prompt += "<|assistant|>\n"

        url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
        headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 1024,
                "temperature": 0.7,
                "return_full_text": False
            }
        }
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code != 200:
            raise Exception(f"HF retornou {response.status_code}: {response.text}")
        
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0].get("generated_text", "").strip()
        elif isinstance(data, dict):
            return data.get("generated_text", "").strip()
        else:
            raise Exception("Resposta inesperada da HF")
    except Exception as e:
        logger.error(f"Hugging Face falhou: {str(e)}")
        raise Exception(f"Hugging Face: {str(e)}")

def obter_resposta(mensagens: list) -> str:
    erros = []
    try:
        return chamar_groq(mensagens)
    except Exception as e:
        erros.append(str(e))
    try:
        return chamar_openrouter(mensagens)
    except Exception as e:
        erros.append(str(e))
    try:
        return chamar_huggingface(mensagens)
    except Exception as e:
        erros.append(str(e))
    
    detalhes = " | ".join(erros)
    raise Exception(f"Todos os provedores falharam. Detalhes: {detalhes}")

# ======================================================
# ENDPOINTS
# ======================================================

@app.get("/status")
async def status():
    return {
        "status": "online",
        "provedores": ["Groq", "OpenRouter", "Hugging Face"],
        "modelo_principal": GROQ_MODEL
    }

@app.post("/chat/texto", response_model=ChatResponse)
async def chat_texto(payload: ChatRequest):
    session_id = payload.sessao_id or str(uuid.uuid4())
    historico = sessoes.get(session_id, [])
    historico.append({"role": "user", "content": payload.texto})
    if len(historico) == 1:
        historico.insert(0, {
            "role": "system",
            "content": "Você é o Lenior, um assistente IA educado, útil e conciso. Responda em português."
        })
    try:
        resposta = obter_resposta(historico)
        historico.append({"role": "assistant", "content": resposta})
        sessoes[session_id] = historico
        return ChatResponse(resposta=resposta, sessao_id=session_id)
    except Exception as e:
        logger.error(f"Erro final: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/chat/audio")
async def chat_audio(
    audio: UploadFile = File(...),
    sessao_id: Optional[str] = Form(None)
):
    session_id = sessao_id or str(uuid.uuid4())
    try:
        audio_bytes = await audio.read()
        arquivo = BytesIO(audio_bytes)
        arquivo.name = audio.filename or "audio.webm"
        
        transcricao = groq_client.audio.transcriptions.create(
            file=arquivo,
            model="whisper-large-v3-turbo",
            response_format="text",
            language="pt"
        )
        texto = transcricao if isinstance(transcricao, str) else transcricao.text
        if not texto or len(texto.strip()) == 0:
            raise Exception("Nenhum texto transcrito.")
        
        historico = sessoes.get(session_id, [])
        historico.append({"role": "user", "content": f"[Áudio] {texto}"})
        if len(historico) == 1:
            historico.insert(0, {
                "role": "system",
                "content": "Você é o Lenior, um assistente IA educado, útil e conciso. Responda em português."
            })
        resposta = obter_resposta(historico)
        historico.append({"role": "assistant", "content": resposta})
        sessoes[session_id] = historico
        return {
            "resposta": resposta,
            "sessao_id": session_id,
            "transcricao": texto
        }
    except Exception as e:
        logger.error(f"Erro no áudio: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Erro no áudio: {str(e)}")

# ======================================================
# SERVE O FRONTEND
# ======================================================
from fastapi.staticfiles import StaticFiles
import os

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

if __name__ == "__main__":
    print("🚀 Lenior Chat rodando em http://localhost:8000")
    print("📡 Provedores: Groq → OpenRouter → Hugging Face")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
