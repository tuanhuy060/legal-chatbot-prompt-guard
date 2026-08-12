"""
Ứng dụng Web Chatbot Pháp Luật & Prompt Guard (FastAPI Backend).
Hỗ trợ Streaming Token (Server-Sent Events), Quản lý Session NoSQL (TinyDB), và Giao diện ChatGPT-style.
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

# Đảm bảo console UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.data.session_store import SessionStore
from src.guard.prompt_guard import PromptGuard
from src.rag.generator import LegalGenerator
from src.rag.legal_ranker import legal_rerank
from src.rag.reranker import LegalReranker
from src.rag.retriever import LegalRetriever

# Khởi tạo FastAPI App
app = FastAPI(
    title="Vietnamese Legal Chatbot & Prompt Guard",
    description="Hệ thống RAG Pháp Luật Việt Nam tích hợp Phòng thủ Bảo mật Đa tầng",
    version="2.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi tạo các Core Components (Lazy / Singleton)
print("[Server] Đang khởi tạo các thành phần hệ thống...")
session_store = SessionStore()
guard = PromptGuard()

# Vector DB & AI Models
retriever = LegalRetriever(db_dir="D:/chroma_legal_db" if Path("D:/chroma_legal_db").exists() else "chroma_legal_db")
reranker = LegalReranker()
generator = LegalGenerator()
print("[Server] Hệ thống đã sẵn sàng phục vụ!")


# ==========================================
# PYDANTIC SCHEMAS
# ==========================================

class CreateSessionRequest(BaseModel):
    user_id: Optional[str] = "user_1"
    title: Optional[str] = "Cuộc trò chuyện mới"


class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = None
    user_id: Optional[str] = "user_1"
    query: str


# ==========================================
# STATIC FILES & WEB ROUTE
# ==========================================

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Giao diện Web chưa được cài đặt.")
    return FileResponse(str(index_file))


# ==========================================
# SESSION MANAGEMENT ENDPOINTS (NoSQL)
# ==========================================

@app.get("/api/sessions")
async def get_sessions(user_id: Optional[str] = "user_1"):
    """Lấy danh sách tất cả các phiên làm việc của người dùng."""
    uid = user_id or "user_1"
    sessions = session_store.list_user_sessions(user_id=uid)
    return {"sessions": sessions}


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    """Tạo một phiên làm việc mới."""
    uid = req.user_id or "user_1"
    session = session_store.create_session(user_id=uid, title=req.title or "Cuộc trò chuyện mới")
    return {"session": session}


@app.get("/api/sessions/{session_id}")
async def get_session_detail(session_id: str, user_id: Optional[str] = "user_1"):
    """Lấy chi tiết và lịch sử tin nhắn của một phiên."""
    uid = user_id or "user_1"
    session = session_store.get_session(session_id, user_id=uid)
    if not session:
        # Nếu chưa tìm thấy thì tìm theo session_id không cần user_id
        session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên làm việc.")
    return {"session": session}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, user_id: Optional[str] = "user_1"):
    """Xóa một phiên làm việc."""
    uid = user_id or "user_1"
    success = session_store.delete_session(session_id, user_id=uid)
    return {"success": success}


@app.get("/api/stats")
async def get_system_stats():
    """Lấy thống kê hệ thống (Vector DB, Model, Security)."""
    collection_count = retriever.vector_store._collection.count() if hasattr(retriever.vector_store, "_collection") else 8727
    security_logs = session_store.get_security_logs(limit=10)
    return {
        "status": "online",
        "vector_chunks": collection_count,
        "embedding_model": "BAAI/bge-m3",
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "llm_model": "Qwen/Qwen2.5-1.5B-Instruct",
        "recent_blocked_attacks": len(security_logs)
    }


@app.get("/api/security-logs")
async def get_security_logs(limit: int = 20):
    """Lấy danh sách các cuộc tấn công bị Prompt Guard chặn."""
    logs = session_store.get_security_logs(limit=limit)
    return {"logs": logs}


# ==========================================
# STREAMING CHAT ENDPOINT (SSE)
# ==========================================

@app.post("/api/chat/stream")
async def stream_chat(req: ChatMessageRequest):
    """
    Xử lý câu hỏi và stream kết quả theo thời gian thực qua Server-Sent Events (SSE).
    Sự kiện bắn ra gồm:
    1. {"type": "guard_result", "is_safe": bool, "risk_level": str, ...}
    2. {"type": "citations", "citations": [...]}
    3. {"type": "token", "token": "..."}
    4. {"type": "done", "full_response": "..."}
    """
    query = req.query.strip()
    session_id = req.session_id
    user_id = req.user_id or "user_1"

    if not query:
        raise HTTPException(status_code=400, detail="Câu hỏi không được để trống.")

    # Kiểm tra phiên làm việc hợp lệ
    session = session_store.get_session(session_id, user_id=user_id) if session_id else None
    if not session:
        # Tự động tạo phiên nếu chưa có
        session = session_store.create_session(user_id=user_id, title=query[:30])
        session_id = session["session_id"]

    def event_generator():
        # Lưu câu hỏi của user vào NoSQL
        session_store.add_message(session_id=session_id, role="user", content=query)

        # ----------------------------------------------------
        # BƯỚC 1: KIỂM DUYỆT BẢO MẬT (PROMPT GUARD)
        # ----------------------------------------------------
        guard_res = guard.inspect(query)
        yield f"data: {json.dumps({'type': 'guard_result', 'is_safe': guard_res.is_safe, 'risk_level': guard_res.risk_level.value, 'risk_score': guard_res.risk_score, 'message': guard_res.message, 'matched_patterns': guard_res.matched_patterns}, ensure_ascii=False)}\n\n"

        if not guard_res.is_safe:
            # Ghi log an ninh vào NoSQL
            session_store.log_security_event(
                user_id=user_id,
                prompt=query,
                risk_level=guard_res.risk_level.value,
                risk_score=guard_res.risk_score,
                matched_rules=guard_res.matched_patterns,
                action_taken="BLOCKED_BY_PROMPT_GUARD"
            )
            blocked_msg = f"⛔ **[CẢNH BÁO BẢO MẬT]** Câu hỏi của bạn bị chặn bởi hệ thống phòng thủ **Prompt Guard** do phát hiện nguy cơ: *{', '.join(guard_res.matched_patterns)}*."
            session_store.add_message(
                session_id=session_id,
                role="assistant",
                content=blocked_msg,
                guard_meta={"blocked": True, "rules": guard_res.matched_patterns}
            )
            yield f"data: {json.dumps({'type': 'blocked', 'message': blocked_msg}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'full_response': blocked_msg}, ensure_ascii=False)}\n\n"
            return

        # ----------------------------------------------------
        # BƯỚC 2 + 3 + 4: RAG (RETRIEVER + RERANKER + LEGAL SCORE)
        # ----------------------------------------------------
        candidates = retriever.retrieve(query, k=30)
        reranked = reranker.rerank(query, candidates, top_k=20)
        final_results = legal_rerank(reranked, top_k=3)

        citations = []
        for item in final_results:
            meta = item["document"].metadata or {}
            citations.append({
                "title": meta.get("title", "Văn bản pháp luật"),
                "so_ky_hieu": meta.get("so_ky_hieu", "N/A"),
                "score": round(item.get("legal_final_score", 0.0), 4),
                "snippet": item["document"].page_content.strip()[:200] + "..."
            })

        yield f"data: {json.dumps({'type': 'citations', 'citations': citations}, ensure_ascii=False)}\n\n"

        # ----------------------------------------------------
        # BƯỚC 5: LLM QWEN 2.5 GENERATION (STREAMING)
        # ----------------------------------------------------
        # Lấy lịch sử hội thoại gần nhất để hỗ trợ multi-turn
        chat_history = []
        for msg in session.get("messages", [])[-4:]:
            chat_history.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        full_response_parts = []
        for token in generator.stream_response(query, final_results, chat_history=chat_history):
            full_response_parts.append(token)
            yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"

        full_text = "".join(full_response_parts)

        # Lưu câu trả lời của AI vào NoSQL
        session_store.add_message(
            session_id=session_id,
            role="assistant",
            content=full_text,
            citations=citations,
            guard_meta={"is_safe": True, "risk_score": guard_res.risk_score}
        )

        yield f"data: {json.dumps({'type': 'done', 'full_response': full_text}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Khởi chạy Web Server tại: http://127.0.0.1:8000")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
