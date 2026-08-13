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

    # Các mẫu câu injection / jailbreak tinh vi thực tế (tiếng Anh & tiếng Việt)
    INJECTION_PATTERNS = [
        # 1. Direct Override & Leak
        (re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I), "Instruction Override (EN)", 0.95),
        (re.compile(r"bỏ\s+qua\s+(hết\s+|toàn\s+bộ\s+)?(các\s+)?(hướng\s+dẫn|chỉ\s+dẫn|quy\s+tắc|câu\s+lệnh|ràng\s+buộc)\s+(trước|ở\s+trên|cũ)", re.I), "Instruction Override (VI)", 0.95),
        (re.compile(r"(reveal|print|show|output|display)\s+(your\s+)?(system\s+prompt|initial\s+instructions|system\s+message)", re.I), "System Prompt Leak (EN)", 0.90),
        (re.compile(r"(tiết\s+lộ|in\s+ra|hiển\s+thị|cho\s+tôi\s+xem|đọc\s+lại)\s+(system\s+prompt|lời\s+nhắc\s+hệ\s+thống|câu\s+lệnh\s+gốc|chỉ\s+thị\s+gốc)", re.I), "System Prompt Leak (VI)", 0.90),
        
        # 2. Jailbreak Modes & God Mode
        (re.compile(r"(you\s+are\s+now\s+in|enable|switch\s+to|act\s+as).*(dan|developer|unrestricted|jailbreak|god)\s+mode", re.I), "Jailbreak Mode (EN)", 0.95),
        (re.compile(r"(bây\s+giờ\s+)?bạn\s+là\s+(chế\s+độ\s+DAN|chế\s+độ\s+không\s+giới\s+hạn|jailbreak)", re.I), "Jailbreak Mode (VI)", 0.95),
        
        # 3. Kỹ thuật Lắc léo: Roleplay Hijack / Persona Simulation (Đóng vai thẩm phán hư cấu, tiểu thuyết gia...)
        (re.compile(r"(hãy\s+đóng\s+vai|tưởng\s+tượng\s+bạn\s+là|giả\s+sử\s+bạn\s+là)\s+.*(không\s+bị\s+ràng\s+buộc|tội\s+phạm|hacker|hư\s+cấu|không\s+tuân\s+theo\s+luật)", re.I), "Hypothetical Roleplay Hijack (VI)", 0.92),
        (re.compile(r"(act\s+as|pretend\s+you\s+are|imagine\s+you\s+are)\s+.*(unrestricted|lawless|evil|villain|fictional\s+character\s+who\s+ignores\s+laws)", re.I), "Hypothetical Roleplay Hijack (EN)", 0.92),
        
        # 4. Kỹ thuật Yêu cầu Hành vi Vi phạm Pháp luật (Trực tiếp & Núp bóng học thuật)
        (re.compile(r"(chỉ|hướng\s+dẫn|dạy|bày|tìm|làm\s+sao\s+để|cách\s+nào\s+để|cách|tôi\s+cần\s+cách).*(trốn\s+(thuế|thế)|lách\s+luật|rửa\s+tiền|hối\s+lộ|làm\s+giả\s+(giấy\s+tờ|con\s+dấu|hồ\s+sơ|sổ\s+đỏ)|qua\s+mặt\s+(công\s+an|thanh\s+tra|cơ\s+quan)|tống\s+tiền|buôn\s+lậu)", re.I), "Direct Illegal Act Assistance (VI)", 0.95),
        (re.compile(r"(how\s+to|teach\s+me|guide\s+me|ways\s+to).*(evade\s+tax|launder\s+money|bribe|bypass\s+law|forge\s+documents|smuggle)", re.I), "Direct Illegal Act Assistance (EN)", 0.95),
        (re.compile(r"(đây\s+chỉ\s+là\s+.*(tiểu\s+thuyết|kịch\s+bản|bài\s+tập|nghiên\s+cứu)|chỉ\s+để\s+nghiên\s+cứu).*(chỉ\s+cách|làm\s+sao\s+để|hướng\s+dẫn|cách).*(trốn\s+thuế|lách\s+luật|rửa\s+tiền|hối\s+lộ|qua\s+mặt|làm\s+giả)", re.I), "Academic/Fiction Obfuscation (VI)", 0.95),
        (re.compile(r"(for\s+.*(educational|research|fictional|academic)\s+purposes).*(how\s+to|explain\s+how|ways\s+to).*(evade\s+tax|launder\s+money|bribe|bypass\s+law|forge)", re.I), "Academic/Fiction Obfuscation (EN)", 0.95),

        # 5. Kỹ thuật Lắc léo: Rule Negation & Gaslighting (Khẳng định luật pháp đã thay đổi / Yêu cầu không cần luật)
        (re.compile(r"(không\s+cần\s+(theo\s+)?luật|bỏ\s+qua\s+luật|không\s+tuân\s+thủ\s+luật|làm\s+trái\s+luật|vượt\s+mặt\s+luật|bất\s+chấp\s+luật|không\s+cần\s+pháp\s+luật)", re.I), "Law Negation Override", 0.92),
        (re.compile(r"(tất\s+cả\s+luật\s+pháp\s+hiện\s+nay\s+đã\s+bị\s+hủy\s+bỏ|quy\s+tắc\s+cũ\s+không\s+còn\s+hiệu\s+lực|chính\s+phủ\s+đã\s+cho\s+phép)", re.I), "Legal Gaslighting (VI)", 0.90),
        (re.compile(r"(all\s+laws\s+are\s+now\s+void|previous\s+rules\s+are\s+cancelled|emergency\s+override\s+code)", re.I), "Emergency Override Gaslighting (EN)", 0.92),

        # 6. Kỹ thuật Lắc léo: Indirect Output Prefix / Force Response Formatting (Ép bot bắt đầu bằng câu xác nhận vi phạm)
        (re.compile(r"(bắt\s+đầu\s+câu\s+trả\s+lời\s+bằng|start\s+your\s+response\s+with)\s*[:\"'].*(tôi\s+đồng\s+ý|tôi\s+sẽ\s+làm\s+theo|i\s+agree|sure\s+thing)", re.I), "Forced Output Prefixing", 0.88),

        # 7. Kỹ thuật Lắc léo: Social Engineering & Data Exfiltration (Dò hỏi lịch sử chat, dữ liệu riêng tư của người khác)
        (re.compile(r"(cho\s+tôi\s+biết|trích\s+xuất|cho\s+tôi\s+thông\s+tin|danh\s+sách|lịch\s+sử|nội\s+dung)\s+.*(khách\s+hàng\s+(khác|đã\s+nói|đã\s+hỏi)|người\s+dùng\s+khác|cuộc\s+trò\s+chuyện|chat\s+history|log\s+hệ\s+thống)", re.I), "Data Exfiltration & Privacy Leak (VI)", 0.92),
        (re.compile(r"(give\s+me|extract|show\s+me|list)\s+.*(other\s+users?|customer\s+data|chat\s+history|database\s+logs|confidential\s+records)", re.I), "Data Exfiltration & Privacy Leak (EN)", 0.92),

        # 8. Code Injection & Scripting
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
