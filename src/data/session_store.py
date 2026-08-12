"""
Module Quản lý NoSQL Database cho Chat Sessions và Security Logs bằng TinyDB.
Hỗ trợ lưu trữ lịch sử hội thoại nhiều lượt (Multi-turn) và Log an ninh Prompt Guard.
"""
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from tinydb import Query, TinyDB


class SessionStore:
    """Quản lý NoSQL Document Database lưu phiên trò chuyện và nhật ký bảo mật."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Ưu tiên lưu ổ D nếu có, hoặc thư mục data/
            if Path("D:/").exists():
                db_dir = Path("D:/legal_nosql_db")
            else:
                db_dir = Path("data/nosql_db")
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "sessions.json")

        self.db_path = db_path
        self.db = TinyDB(self.db_path, ensure_ascii=False, indent=2)
        self.sessions_table = self.db.table("chat_sessions")
        self.security_table = self.db.table("security_logs")
        print(f"[SessionStore] Khởi tạo NoSQL Session Database tại: {self.db_path}")

    # ==========================================
    # SESSION & CHAT MANAGEMENT
    # ==========================================

    def create_session(self, user_id: str = "default_user", title: str = "Cuộc trò chuyện mới") -> dict[str, Any]:
        """Tạo một phiên làm việc mới."""
        session_id = str(uuid.uuid4())[:8]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session_doc = {
            "session_id": session_id,
            "user_id": user_id,
            "title": title,
            "created_at": now_str,
            "updated_at": now_str,
            "messages": []
        }
        self.sessions_table.insert(session_doc)
        return session_doc

    def get_session(self, session_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Lấy chi tiết một phiên làm việc (kèm xác thực User Isolation)."""
        Q = Query()
        if user_id:
            res = self.sessions_table.get((Q.session_id == session_id) & (Q.user_id == user_id))
        else:
            res = self.sessions_table.get(Q.session_id == session_id)
        return res

    def list_user_sessions(self, user_id: str = "default_user") -> list[dict[str, Any]]:
        """Liệt kê tất cả các phiên làm việc của một người dùng cụ thể."""
        Q = Query()
        sessions = self.sessions_table.search(Q.user_id == user_id)
        # Sắp xếp phiên mới nhất lên đầu
        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return sessions

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: Optional[list[dict[str, Any]]] = None,
        guard_meta: Optional[dict[str, Any]] = None
    ) -> bool:
        """Thêm một tin nhắn vào lịch sử phiên làm việc."""
        Q = Query()
        session = self.sessions_table.get(Q.session_id == session_id)
        if not session:
            return False

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg_id = str(uuid.uuid4())[:8]
        msg_obj = {
            "id": msg_id,
            "role": role,  # "user" | "assistant" | "system"
            "content": content,
            "timestamp": now_str,
            "citations": citations or [],
            "guard_meta": guard_meta or {}
        }

        messages = session.get("messages", [])
        messages.append(msg_obj)

        # Cập nhật tiêu đề phiên nếu là câu hỏi đầu tiên của user
        title = session.get("title", "Cuộc trò chuyện mới")
        if role == "user" and len(messages) <= 2 and (title == "Cuộc trò chuyện mới" or not title):
            title = content[:40] + ("..." if len(content) > 40 else "")

        self.sessions_table.update(
            {"messages": messages, "updated_at": now_str, "title": title},
            Q.session_id == session_id
        )
        return True

    def delete_session(self, session_id: str, user_id: Optional[str] = None) -> bool:
        """Xóa một phiên làm việc."""
        Q = Query()
        if user_id:
            removed = self.sessions_table.remove((Q.session_id == session_id) & (Q.user_id == user_id))
        else:
            removed = self.sessions_table.remove(Q.session_id == session_id)
        return len(removed) > 0

    # ==========================================
    # SECURITY AUDIT LOGGING
    # ==========================================

    def log_security_event(
        self,
        user_id: str,
        prompt: str,
        risk_level: str,
        risk_score: float,
        matched_rules: list[str],
        action_taken: str = "BLOCKED"
    ) -> None:
        """Ghi nhận nhật ký tấn công của Prompt Guard để phục vụ kiểm toán an ninh."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = {
            "id": str(uuid.uuid4())[:8],
            "user_id": user_id,
            "prompt": prompt,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "matched_rules": matched_rules,
            "action": action_taken,
            "timestamp": now_str
        }
        self.security_table.insert(log_entry)

    def get_security_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Lấy danh sách các vụ tấn công bị chặn gần nhất."""
        logs = self.security_table.all()
        logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return logs[:limit]
