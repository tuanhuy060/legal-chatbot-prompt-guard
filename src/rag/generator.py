"""
Module Tích hợp LLM Não Qwen 2.5 (Qwen/Qwen2.5-1.5B-Instruct) với Legal Chain-of-Thought Prompt.
Tự động suy luận pháp lý 3 bước: Căn cứ -> Phân tích -> Kết luận dứt khoát.
"""
import os
import re
import sys
from pathlib import Path
from threading import Thread
from typing import Any, Generator, Optional

# Đảm bảo UTF-8 an toàn trên Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Tự động trỏ cache HuggingFace sang ổ D (nếu có) để tránh đầy ổ C
if "HF_HOME" not in os.environ and Path("D:/").exists():
    os.environ["HF_HOME"] = "D:/hf_cache"

import torch
# Tối ưu hóa số luồng CPU cho tốc độ suy luận nhanh nhất
if not torch.cuda.is_available():
    cpu_cores = os.cpu_count() or 4
    torch.set_num_threads(min(cpu_cores, 8))

from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer, TextStreamer


class OutputSanitizer:
    """Tầng kiểm soát bảo mật đầu ra: Quét và che mờ PII (CCCD, SĐT, STK, Email...)."""

    PII_PATTERNS = [
        (re.compile(r"\b\d{9}\b|\b\d{12}\b"), "[REDACTED_CCCD]"),
        (re.compile(r"(\+84|0)(3|5|7|8|9)\d{8}\b"), "[REDACTED_PHONE]"),
        (re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}(?:[-\s]?\d{4})?\b"), "[REDACTED_BANK_ACCOUNT]"),
        (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[REDACTED_EMAIL]"),
    ]

    @classmethod
    def sanitize(cls, text: str) -> tuple[str, list[str]]:
        detected = []
        sanitized_text = text

        for pattern, mask in cls.PII_PATTERNS:
            matches = pattern.findall(sanitized_text)
            if matches:
                detected.append(mask)
                sanitized_text = pattern.sub(mask, sanitized_text)

        return sanitized_text, detected


class LegalGenerator:
    """Động cơ Tạo câu trả lời pháp lý bằng Não LLM Qwen 2.5 với Legal CoT Reasoning."""

    MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"
    MIN_RERANKER_CONFIDENCE = 0.500

    SYSTEM_PROMPT = (
        "Bạn là Luật sư Chuyên gia Tư vấn Pháp luật Việt Nam chuẩn mực, trung thực và sắc sảo.\n"
        "QUY TẮC BẮT BUỘC KHI TRẢ LỜI:\n"
        "1. Đọc kỹ phần [BỐI CẢNH VĂN BẢN PHÁP LUẬT] được cung cấp dưới đây để trả lời câu hỏi.\n"
        "2. Cấu trúc câu trả lời BẮT BUỘC gồm 3 phần rõ ràng:\n"
        "   - 📌 CĂN CỨ PHÁP LÝ: Nêu rõ Tên văn bản luật, Số ký hiệu, Điều, Khoản, Điểm điều chỉnh trực tiếp vấn đề.\n"
        "   - ⚖️ PHÂN TÍCH & ĐỐI CHIẾU: Trích dẫn nội dung quy phạm và phân tích áp dụng vào trường hợp của người dùng.\n"
        "   - 🎯 KẾT LUẬN: Khẳng định dứt khoát (ĐƯỢC PHÉP / KHÔNG ĐƯỢC PHÉP / VI PHẠM PHÁP LUẬT / ĐỦ ĐIỀU KIỆN...).\n"
        "3. Tuyệt đối không tự bịa đặt điều luật không có trong bối cảnh.\n"
        "4. Nếu trong bối cảnh không có quy định giải đáp câu hỏi, hãy từ chối: Kho dữ liệu hiện chưa có văn bản thuộc lĩnh vực này.\n"
        "5. Luôn kết thúc bằng: '⚠️ LƯU Ý: Thông tin trên chỉ mang tính chất tham khảo.'"
    )

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = None
        self.model = None
        self._is_loaded = False

    def load_model(self):
        """Khởi tạo và nạp mô hình Qwen 2.5 vào RAM / VRAM."""
        if self._is_loaded and self.model is not None:
            return

        print(f"[Generator] Đang nạp mô hình LLM '{self.model_name}' trên {self.device.upper()} (lưu tại {os.environ.get('HF_HOME', 'default')})...")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            low_cpu_mem_usage=True
        ).to(self.device)
        self.model.eval()
        self._is_loaded = True
        print("[Generator] Não LLM Qwen 2.5 đã sẵn sàng.")

    def generate_response(
        self,
        query: str,
        retrieved_docs: list[dict[str, Any]],
        stream: bool = False
    ) -> str:
        """Sinh câu trả lời với sự kiểm tra nghiêm ngặt tính liên quan của bối cảnh."""
        # 1. Kiểm tra Out-of-Domain (Không có văn bản liên quan)
        if not retrieved_docs or retrieved_docs[0].get("reranker_score", 0.0) < self.MIN_RERANKER_CONFIDENCE:
            msg = (
                "Kính gửi Quý người dùng,\n\n"
                "Hệ thống đã tra cứu trong kho dữ liệu nhưng KHÔNG TÌM THẤY văn bản quy phạm pháp luật phù hợp để giải đáp câu hỏi của bạn.\n"
                "(Kho dữ liệu hiện tại chưa có văn bản thuộc lĩnh vực bạn đang hỏi).\n\n"
                "⚠️ KHUYẾN NGHỊ:\n"
                "Hệ thống từ chối đưa ra kết luận để tránh cung cấp thông tin sai lệch (Hallucination). "
                "Vui lòng bổ sung thêm văn bản luật tương ứng vào cơ sở dữ liệu."
            )
            if stream:
                print(msg)
            return msg

        # 2. Đảm bảo model đã được nạp
        if not self._is_loaded:
            self.load_model()

        # 3. Đóng gói context từ RAG
        context_parts = []
        for i, item in enumerate(retrieved_docs[:3], 1):
            doc = item["document"]
            meta = doc.metadata or {}
            title = meta.get("title", "Văn bản")
            symbol = meta.get("so_ky_hieu", "")
            context_parts.append(f"--- [VĂN BẢN {i}: {title} (Số: {symbol})] ---\n{doc.page_content.strip()}")
        context_str = "\n\n".join(context_parts)

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"[BỐI CẢNH VĂN BẢN PHÁP LUẬT]:\n{context_str}\n\n"
                    f"[CÂU HỎI]:\n{query}\n\n"
                    f"Hãy trả lời theo đúng cấu trúc 3 phần (Căn cứ pháp lý -> Phân tích & đối chiếu -> Kết luận):"
                )
            }
        ]

        # 4. Sinh văn bản qua Qwen 2.5
        text_prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        model_inputs = self.tokenizer([text_prompt], return_tensors="pt").to(self.device)

        streamer = TextStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True) if stream else None

        with torch.no_grad():
            generated_ids = self.model.generate(
                **model_inputs,
                max_new_tokens=1000,
                do_sample=False,
                repetition_penalty=1.1,
                streamer=streamer
            )

        generated_ids = [
            output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]
        response_text = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

        sanitized_response, _ = OutputSanitizer.sanitize(response_text)
        return sanitized_response

    def stream_response(
        self,
        query: str,
        retrieved_docs: list[dict[str, Any]],
        chat_history: Optional[list[dict[str, str]]] = None
    ) -> Generator[str, None, None]:
        """Stream từng token câu trả lời qua Generator (phục vụ Server-Sent Events)."""
        # 1. Kiểm tra Out-of-Domain
        if not retrieved_docs or retrieved_docs[0].get("reranker_score", 0.0) < self.MIN_RERANKER_CONFIDENCE:
            yield (
                "Kính gửi Quý người dùng,\n\n"
                "Hệ thống đã tra cứu trong kho dữ liệu nhưng **KHÔNG TÌM THẤY** văn bản quy phạm pháp luật phù hợp để giải đáp câu hỏi của bạn.\n"
                "(Kho dữ liệu hiện tại chưa có văn bản thuộc lĩnh vực bạn đang hỏi).\n\n"
                "⚠️ **KHUYẾN NGHỊ:**\n"
                "Hệ thống từ chối đưa ra kết luận để tránh cung cấp thông tin sai lệch (Hallucination). "
                "Vui lòng bổ sung thêm văn bản luật tương ứng vào cơ sở dữ liệu."
            )
            return

        # 2. Đảm bảo model đã load
        if not self._is_loaded:
            self.load_model()

        # 3. Đóng gói context gọn gàng (Top 2 văn bản)
        context_parts = []
        for i, item in enumerate(retrieved_docs[:2], 1):
            doc = item["document"]
            meta = doc.metadata or {}
            title = meta.get("title", "Văn bản")
            symbol = meta.get("so_ky_hieu", "")
            context_parts.append(f"--- [VĂN BẢN {i}: {title} (Số: {symbol})] ---\n{doc.page_content.strip()}")
        context_str = "\n\n".join(context_parts)

        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        # Hỗ trợ multi-turn chat history nếu có
        if chat_history:
            for turn in chat_history[-2:]:  # Lấy 1 cặp hỏi-đáp gần nhất
                messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})

        messages.append({
            "role": "user",
            "content": (
                f"[BỐI CẢNH VĂN BẢN PHÁP LUẬT]:\n{context_str}\n\n"
                f"[CÂU HỎI]:\n{query}\n\n"
                f"Hãy trả lời theo đúng cấu trúc 3 phần (Căn cứ pháp lý -> Phân tích & đối chiếu -> Kết luận):"
            )
        })

        text_prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        model_inputs = self.tokenizer([text_prompt], return_tensors="pt").to(self.device)

        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        generation_kwargs = dict(
            **model_inputs,
            max_new_tokens=1000,
            do_sample=False,
            repetition_penalty=1.1,
            streamer=streamer
        )

        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        for new_text in streamer:
            yield new_text

        thread.join()
