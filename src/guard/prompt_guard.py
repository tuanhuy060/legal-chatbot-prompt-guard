"""
Module phát hiện và ngăn chặn tấn công Prompt Injection / Jailbreak đối với Legal Chatbot.
"""
import re
from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    ATTACK = "attack"


@dataclass
class GuardResult:
    is_safe: bool
    risk_level: RiskLevel
    risk_score: float
    matched_patterns: list[str]
    sanitized_prompt: str
    message: str


class PromptGuard:
    """Tầng kiểm duyệt bảo mật đầu vào cho Legal Chatbot."""

    # Các mẫu câu injection / jailbreak phổ biến tiếng Anh & tiếng Việt
    INJECTION_PATTERNS = [
        (re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I), "Instruction Override (EN)", 0.95),
        (re.compile(r"bỏ\s+qua\s+(hết\s+|toàn\s+bộ\s+)?(các\s+)?(hướng\s+dẫn|chỉ\s+dẫn|quy\s+tắc|câu\s+lệnh)\s+(trước|ở\s+trên)", re.I), "Instruction Override (VI)", 0.95),
        (re.compile(r"(reveal|print|show|output|display)\s+(your\s+)?(system\s+prompt|initial\s+instructions|system\s+message)", re.I), "System Prompt Leak (EN)", 0.90),
        (re.compile(r"(tiết\s+lộ|in\s+ra|hiển\s+thị|cho\s+tôi\s+xem)\s+(system\s+prompt|lời\s+nhắc\s+hệ\s+thống|câu\s+lệnh\s+gốc)", re.I), "System Prompt Leak (VI)", 0.90),
        (re.compile(r"(you\s+are\s+now\s+in|enable|switch\s+to|act\s+as).*(dan|developer|unrestricted|jailbreak|god)\s+mode", re.I), "Jailbreak Mode (EN)", 0.95),
        (re.compile(r"(bây\s+giờ\s+)?bạn\s+là\s+(chế\s+độ\s+DAN|chế\s+độ\s+không\s+giới\s+hạn|jailbreak)", re.I), "Jailbreak Mode (VI)", 0.95),
        (re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.I | re.S), "HTML/Script Injection", 0.85),
        (re.compile(r"(DROP\s+TABLE|SELECT\s+\*\s+FROM|UNION\s+SELECT)", re.I), "SQL Injection Pattern", 0.85),
    ]

    def __init__(self, threshold_attack: float = 0.80, threshold_suspicious: float = 0.50):
        self.threshold_attack = threshold_attack
        self.threshold_suspicious = threshold_suspicious

    def inspect(self, prompt: str) -> GuardResult:
        """Kiểm tra và đánh giá mức độ rủi ro của câu hỏi từ người dùng."""
        if not prompt or not prompt.strip():
            return GuardResult(
                is_safe=True,
                risk_level=RiskLevel.SAFE,
                risk_score=0.0,
                matched_patterns=[],
                sanitized_prompt="",
                message="Prompt rỗng"
            )

        matched_rules = []
        max_score = 0.0

        for pattern, rule_name, weight in self.INJECTION_PATTERNS:
            if pattern.search(prompt):
                matched_rules.append(rule_name)
                if weight > max_score:
                    max_score = weight

        # Phân loại mức độ rủi ro
        if max_score >= self.threshold_attack:
            risk_level = RiskLevel.ATTACK
            is_safe = False
            message = f"Phát hiện dấu hiệu tấn công Prompt Injection: {', '.join(matched_rules)}"
        elif max_score >= self.threshold_suspicious:
            risk_level = RiskLevel.SUSPICIOUS
            is_safe = True
            message = f"Cảnh báo prompt đáng ngờ: {', '.join(matched_rules)}"
        else:
            risk_level = RiskLevel.SAFE
            is_safe = True
            message = "Prompt an toàn"

        # Loại bỏ các ký tự điều khiển lạ
        sanitized = prompt.strip()

        return GuardResult(
            is_safe=is_safe,
            risk_level=risk_level,
            risk_score=max_score,
            matched_patterns=matched_rules,
            sanitized_prompt=sanitized,
            message=message
        )
