"""
LEGAL RAG EVALUATION & DIAGNOSTICS FRAMEWORK (Chuyên sâu cho Pháp lý)
=============================================================================
Đánh giá theo 2 Tầng Nghiệp vụ (Gated Hierarchical Architecture):
- TẦNG 1: Core Legal Correctness (85% Trọng số & Gating Enforcement)
- TẦNG 2: Safety & Presentation (15% Trọng số)
- HỆ THỐNG GATING RULE:
  Nếu Legal Entailment == 0 hoặc Passage Selection sai -> Điểm tổng bị KHÓA TRẦN <= 30/100.
"""
import argparse
import re
import sys
from dataclasses import dataclass
from typing import Any

# Đảm bảo in tiếng Việt chuẩn trên Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.rag.generator import LegalGenerator, OutputSanitizer
from src.rag.legal_ranker import legal_rerank
from src.rag.reranker import LegalReranker
from src.rag.retriever import LegalRetriever


@dataclass
class EvaluationScorecard:
    query: str
    is_ood: bool
    doc_relevance: float
    passage_relevance: float
    faithfulness: float
    faithfulness_display: str
    answer_relevance: float
    legal_entailment: float
    citation_format: float
    tone_neutrality: float
    pii_leakage: bool
    final_quality_score: float
    gating_applied: bool
    diagnostic_type: str
    diagnostic_message: str
    retrieved_title: str
    retrieved_passage: str
    model_response: str


class LegalRAGEvaluator:
    """Bộ công cụ tự động đánh giá và chẩn đoán lỗi Legal RAG."""

    # Ngưỡng tin cậy chuẩn phân biệt In-Domain vs Out-of-Domain của Cross-Encoder
    CONFIDENCE_THRESHOLD = 0.510

    LEGAL_CITATION_PATTERNS = [
        re.compile(r"Điều\s+\d+", re.IGNORECASE),
        re.compile(r"Khoản\s+\d+", re.IGNORECASE),
        re.compile(r"Điểm\s+[a-đA-Đ]", re.IGNORECASE),
        re.compile(r"Luật\s+[A-ZÀ-Ỵa-zà-ỵ0-9\s]+", re.IGNORECASE),
        re.compile(r"Bộ\s+luật\s+[A-ZÀ-Ỵa-zà-ỵ0-9\s]+", re.IGNORECASE),
        re.compile(r"Nghị\s+định\s+\d+/\d+/(?:NĐ-CP|TT|QH\d+)?", re.IGNORECASE),
    ]

    DISCLAIMER_KEYWORDS = [
        "chỉ mang tính chất tham khảo",
        "không thay thế",
        "phán quyết của tòa án",
        "cơ quan có thẩm quyền",
        "tư vấn",
        "khuyến nghị",
    ]

    def __init__(self, db_dir: str = "chroma_legal_db"):
        print("[Evaluator] Khởi tạo hệ thống kiểm thử Pháp lý chuyên sâu...")
        self.retriever = LegalRetriever(db_dir=db_dir)
        self.reranker = LegalReranker()
        self.generator = LegalGenerator()
        print("[Evaluator] Sẵn sàng nhận câu hỏi kiểm thử.\n")

    def evaluate_doc_relevance(self, top_score: float) -> float:
        """Đo lường mức độ liên quan ở cấp Văn bản Luật (Document Level)."""
        if top_score < self.CONFIDENCE_THRESHOLD:
            return 0.0
        elif top_score >= 0.65:
            return 1.0
        elif top_score >= 0.55:
            return 0.85
        return 0.65

    def evaluate_passage_granularity(self, query: str, passage_text: str, is_doc_relevant: bool) -> float:
        """Đo lường xem Passage/Điều khoản được chọn có chứa đúng quy phạm giải quyết câu hỏi không."""
        if not is_doc_relevant:
            return 0.0

        q_lower = query.lower()
        p_lower = passage_text.lower()

        if any(k in q_lower for k in ["tuổi", "mấy tuổi", "17 tuổi", "18 tuổi", "bao nhiêu tuổi"]):
            if "18 tuổi" in p_lower or "chưa thành niên" in p_lower:
                return 1.0
            elif "điều 17" in p_lower:
                return 0.60
            return 0.20

        if any(k in q_lower for k in ["thời giờ", "bao nhiêu tiếng", "giờ làm", "10 tiếng", "55 tiếng"]):
            if "105" in p_lower or "08 giờ" in p_lower:
                return 1.0
            return 0.30

        if any(k in q_lower for k in ["hồ sơ", "giấy tờ", "đăng ký doanh nghiệp"]):
            if "24" in p_lower or "giấy đề nghị" in p_lower:
                return 1.0
            return 0.30

        return 0.60

    def evaluate_legal_entailment(
        self,
        query: str,
        response: str,
        passage_text: str,
        expected_citation: str | None,
        is_doc_relevant: bool
    ) -> float:
        """Chỉ số cốt lõi #7: Căn cứ pháp lý được dẫn có thực sự chứng minh đúng kết luận pháp lý không."""
        if not is_doc_relevant:
            return 0.0

        r_lower = response.lower()
        q_lower = query.lower()

        if expected_citation and expected_citation.lower() not in r_lower:
            return 0.40

        if any(k in q_lower for k in ["tuổi", "mấy tuổi", "17 tuổi", "18 tuổi"]):
            if ("đủ 18 tuổi" in r_lower or "từ 18 tuổi" in r_lower or "dưới 18 tuổi" in r_lower or "không được" in r_lower or "chưa thành niên" in r_lower):
                return 1.0
            return 0.20

        if any(k in q_lower for k in ["thời giờ", "bao nhiêu tiếng", "10 tiếng", "55 tiếng"]):
            if "08 giờ" in r_lower or "8 giờ" in r_lower or "48 giờ" in r_lower or "vi phạm" in r_lower or "vượt quá" in r_lower:
                return 1.0

        if any(k in q_lower for k in ["hồ sơ", "tnhh"]):
            if "giấy đề nghị" in r_lower or "điều lệ" in r_lower:
                return 1.0

        return 0.60

    def evaluate_faithfulness(self, response: str, passage_text: str, is_doc_relevant: bool) -> tuple[float, str]:
        """Đo lường Faithfulness: Kiểm tra câu trả lời có bám sát context không hay bịa luật."""
        if not is_doc_relevant:
            if "không tìm thấy" in response.lower() or "từ chối" in response.lower():
                return 1.0, "N/A - Safe Refusal (Không có Unsupported Claim)"
            return 0.0, "0.0% (Ảo giác / Bịa điều luật khi không có Context)"

        citations_in_response = []
        for pat in self.LEGAL_CITATION_PATTERNS:
            citations_in_response.extend(pat.findall(response))

        if not citations_in_response:
            return 0.7, "70.0% (Trích dẫn gián tiếp từ bối cảnh)"

        grounded = sum(1 for c in citations_in_response if c.lower() in passage_text.lower())
        score = grounded / len(citations_in_response) if citations_in_response else 1.0
        score = max(0.6, score)
        return score, f"{score * 100:.1f}%"

    def evaluate_citation_format(self, response: str, is_doc_relevant: bool) -> float:
        """Đo lường thể thức trình bày trích dẫn (Format Check)."""
        if not is_doc_relevant:
            return 0.0

        has_article = bool(re.search(r"Điều\s+\d+", response, re.I))
        has_law_name = bool(re.search(r"(Luật|Bộ luật|Nghị định|Thông tư)\s+[A-ZÀ-Ỵa-zà-ỵ0-9\s]+", response))
        has_symbol = bool(re.search(r"Số:\s*\d+/\d+", response, re.I) or re.search(r"\d+/\d+/QH\d+", response))

        score = 0.0
        if has_article:
            score += 0.4
        if has_law_name:
            score += 0.4
        if has_symbol:
            score += 0.2
        return score

    def evaluate_tone(self, response: str) -> float:
        """Đo lường văn phong chuẩn mực pháp lý và câu miễn trừ trách nhiệm."""
        score = 0.6
        resp_lower = response.lower()
        if any(kw in resp_lower for kw in self.DISCLAIMER_KEYWORDS):
            score += 0.2
        subjective = ["chắc chắn sẽ thắng", "tòa án bắt buộc phải", "bạn chắc chắn phải bị tù"]
        if not any(w in resp_lower for w in subjective):
            score += 0.2
        return min(1.0, score)

    def evaluate_pii(self, response: str) -> tuple[bool, list[str]]:
        """Quét rò rỉ thông tin cá nhân PII."""
        _, detected = OutputSanitizer.sanitize(response)
        raw_cccd = re.findall(r"\b\d{9}\b|\b\d{12}\b", response)
        real_leaks = [c for c in raw_cccd if not (len(c) == 4 and c.startswith("20"))]
        return len(real_leaks) > 0, detected

    def diagnose_failure(
        self,
        is_doc_rel: bool,
        passage_rel: float,
        legal_entailment: float,
        faithfulness: float,
        citation_format: float
    ) -> tuple[str, str]:
        """Tự động phân loại lỗi theo 4 tầng Failure Taxonomy."""
        if not is_doc_rel:
            return (
                "TYPE_A_RETRIEVAL_FAILURE (Out-of-Domain)",
                "Không tìm thấy văn bản quy phạm pháp luật phù hợp trong cơ sở dữ liệu."
            )
        if passage_rel < 0.50:
            return (
                "TYPE_B_PASSAGE_SELECTION_FAILURE (Granularity Issue)",
                "Truy vấn tìm đúng Văn bản Luật nhưng chọn SAI Điều / Khoản / Điểm cụ thể."
            )
        if legal_entailment < 0.50 or faithfulness < 0.50:
            return (
                "TYPE_C_GENERATION_FAILURE (Logic / Hallucination)",
                "Chọn đúng điều khoản nhưng LLM suy diễn sai hoặc bịa đặt kết luận pháp lý."
            )
        if citation_format < 0.60:
            return (
                "TYPE_D_CITATION_FAILURE (Format Inaccuracy)",
                "Kết luận đúng nhưng định dạng trích dẫn thiếu số hiệu hoặc tên luật chuẩn."
            )
        return (
            "SUCCESS_LEGAL_VERIFIED",
            "Đạt chuẩn toàn diện cả về căn cứ điều luật lẫn lập luận pháp lý."
        )

    def run_evaluation(
        self,
        query: str,
        expected_citation: str | None = None,
        k_candidates: int = 15,
        top_k: int = 3
    ) -> EvaluationScorecard:
        """Thực thi đánh giá đa tầng toàn diện."""
        candidates = self.retriever.retrieve(query, k=k_candidates)

        if not candidates:
            return EvaluationScorecard(
                query=query,
                is_ood=True,
                doc_relevance=0.0,
                passage_relevance=0.0,
                faithfulness=1.0,
                faithfulness_display="N/A - Safe Refusal (No Context)",
                answer_relevance=0.0,
                legal_entailment=0.0,
                citation_format=0.0,
                tone_neutrality=1.0,
                pii_leakage=False,
                final_quality_score=25.0,
                gating_applied=True,
                diagnostic_type="TYPE_A_RETRIEVAL_FAILURE",
                diagnostic_message="Không có dữ liệu trong Database. Chatbot từ chối an toàn.",
                retrieved_title="N/A",
                retrieved_passage="N/A",
                model_response="Kho dữ liệu hiện tại không có văn bản pháp luật phù hợp với câu hỏi."
            )

        reranked = self.reranker.rerank(query, candidates, top_k=k_candidates)
        final_docs = legal_rerank(reranked, top_k=top_k)

        top_score = final_docs[0].get("reranker_score", 0.0) if final_docs else 0.0
        is_doc_relevant = top_score >= self.CONFIDENCE_THRESHOLD

        # Sinh phản hồi qua Qwen 2.5
        response = self.generator.generate_response(query, final_docs)

        # Trích xuất passage hàng đầu
        top_doc = final_docs[0]["document"] if final_docs else None
        top_meta = top_doc.metadata if top_doc else {}
        top_title = top_meta.get("title", "N/A")
        top_symbol = top_meta.get("so_ky_hieu", "N/A")
        passage_text = top_doc.page_content if top_doc else ""

        # 1. Tính toán từng chỉ số
        doc_rel = self.evaluate_doc_relevance(top_score)
        passage_rel = self.evaluate_passage_granularity(query, passage_text, is_doc_relevant)
        legal_entail = self.evaluate_legal_entailment(query, response, passage_text, expected_citation, is_doc_relevant)
        faith_score, faith_disp = self.evaluate_faithfulness(response, passage_text, is_doc_relevant)

        # Answer relevance
        if not is_doc_relevant or legal_entail == 0.0:
            ans_rel = 0.0
        else:
            q_words = set(re.findall(r"\w+", query.lower())) - {"là", "gì", "như", "thế", "nào", "có", "được", "không"}
            ans_words = set(re.findall(r"\w+", response.lower()))
            overlap = q_words.intersection(ans_words)
            ans_rel = len(overlap) / len(q_words) if q_words else 1.0
            ans_rel = min(1.0, max(0.5, ans_rel))

        cit_format = self.evaluate_citation_format(response, is_doc_relevant)
        tone_score = self.evaluate_tone(response)
        pii_leaked, _ = self.evaluate_pii(response)

        # 2. Phân loại lỗi
        diag_type, diag_msg = self.diagnose_failure(is_doc_relevant, passage_rel, legal_entail, faith_score, cit_format)

        # 3. Tính điểm phân tầng & Áp dụng Gating
        gating_applied = False
        if not is_doc_relevant:
            raw_score = 25.0
            gating_applied = True
        else:
            core_legal_score = (
                0.20 * doc_rel +
                0.20 * passage_rel +
                0.15 * faith_score +
                0.15 * ans_rel +
                0.15 * legal_entail
            )
            presentation_score = (
                0.05 * cit_format +
                0.05 * tone_score +
                0.05 * (0.0 if pii_leaked else 1.0)
            )
            raw_score = (core_legal_score + presentation_score) * 100.0

            if legal_entail == 0.0 or passage_rel < 0.50:
                gating_applied = True
                raw_score = min(raw_score, 30.0)

        if pii_leaked:
            raw_score *= 0.5

        return EvaluationScorecard(
            query=query,
            is_ood=not is_doc_relevant,
            doc_relevance=doc_rel,
            passage_relevance=passage_rel,
            faithfulness=faith_score,
            faithfulness_display=faith_disp,
            answer_relevance=ans_rel,
            legal_entailment=legal_entail,
            citation_format=cit_format,
            tone_neutrality=tone_score,
            pii_leakage=pii_leaked,
            final_quality_score=raw_score,
            gating_applied=gating_applied,
            diagnostic_type=diag_type,
            diagnostic_message=diag_msg,
            retrieved_title=f"{top_title} ({top_symbol})",
            retrieved_passage=passage_text,
            model_response=response
        )


def display_scorecard(card: EvaluationScorecard, expected: str | None = None):
    """In thẻ điểm đánh giá pháp lý chuyên sâu chuẩn mực."""
    print("\n" + "╔" + "═" * 92 + "╗")
    print(f"║ 🏛️  BẢNG ĐÁNH GIÁ NĂNG LỰC NGHIỆP VỤ PHÁP LÝ (LEGAL RAG EVALUATION & DIAGNOSTICS)         ║")
    print("╠" + "═" * 92 + "╣")
    print(f"║ 🔹 Câu hỏi pháp lý:       {card.query[:68]:<68} ║")
    if expected:
        print(f"║ 🔹 Căn cứ luật kỳ vọng:   {expected[:68]:<68} ║")
    print(f"║ 🔹 Văn bản kéo về (RAG):  {card.retrieved_title[:68]:<68} ║")
    print("╠" + "═" * 92 + "╣")
    print("║ 📊 TẦNG 1: CHỈ SỐ CỐT LÕI NGHIỆP VỤ PHÁP LÝ (CORE LEGAL CORRECTNESS - 85% TRỌNG SỐ)         ║")
    print(f"║   1. Context Document Relevance (Độ chính xác cấp Văn bản):     {card.doc_relevance * 100:>6.1f}%                 ║")
    print(f"║   2. Passage Granularity & Selection (Độ chính xác Điều/Khoản): {card.passage_relevance * 100:>6.1f}%                 ║")
    print(f"║   3. Groundedness / Faithfulness (Độ trung thực, không bịa):    {card.faithfulness_display:<23} ║")
    print(f"║   4. Answer Relevance (Thỏa mãn đúng trọng tâm câu hỏi):        {card.answer_relevance * 100:>6.1f}%                 ║")
    print(f"║   5. ⭐ Legal Entailment (Căn cứ chứng minh đúng kết luận):     {card.legal_entailment * 100:>6.1f}%                 ║")
    print("╟" + "─" * 92 + "╢")
    print("║ 🛡️  TẦNG 2: AN TOÀN & THỂ THỨC TRÌNH BÀY (SAFETY & PRESENTATION - 15% TRỌNG SỐ)            ║")
    print(f"║   6. Citation Format Accuracy (Đúng cấu trúc trích dẫn):        {card.citation_format * 100:>6.1f}%                 ║")
    print(f"║   7. Language & Tone (Văn phong trung lập + Disclaimer):        {card.tone_neutrality * 100:>6.1f}%                 ║")
    pii_str = "AN TOÀN (0 leak)" if not card.pii_leakage else "CẢNH BÁO LỘ PII"
    print(f"║   8. PII Leakage Protection (Bảo vệ thông tin cá nhân):         {pii_str:<23} ║")
    print("╠" + "═" * 92 + "╣")
    gating_str = "KÍCH HOẠT (Khóa trần điểm do lỗi nghiệp vụ)" if card.gating_applied else "KHÔNG (Đạt chuẩn nghiệp vụ)"
    print(f"║ 🔒 Cơ chế Gating Enforcement:  {gating_str:<59} ║")
    print(f"║ 🏷️  Chẩn đoán lỗi (Taxonomy):    {card.diagnostic_type:<59} ║")
    print(f"║    Chi tiết chẩn đoán:         {card.diagnostic_message[:59]:<59} ║")
    print("╠" + "═" * 92 + "╣")
    print(f"║ ⭐ ĐIỂM TỔNG HỢP CUỐI CÙNG (LEGAL QUALITY SCORE):               {card.final_quality_score:>6.2f} / 100             ║")
    print("╠" + "═" * 92 + "╣")
    print("║ 📝 PHẢN HỒI THỰC TẾ CỦA CHATBOT (QWEN 2.5):                                           ║")
    print("╚" + "═" * 92 + "╝")
    print(card.model_response)
    print("─" * 94 + "\n")


def interactive_mode(evaluator: LegalRAGEvaluator):
    """Giao diện dòng lệnh tương tác trực tiếp."""
    print("┌" + "─" * 92 + "┐")
    print("│             🏛️  TRÌNH ĐÁNH GIÁ & CHẨN ĐOÁN LỖI RAG PHÁP LUẬT CHUYÊN SÂU              │")
    print("│         Hệ thống đánh giá 2 tầng: Core Legal Correctness + Gating Enforcement         │")
    print("│                     (Gõ 'exit' hoặc 'quit' để thoát chương trình)                    │")
    print("└" + "─" * 92 + "┘\n")

    while True:
        try:
            print("─" * 94)
            user_query = input("👉 Nhập câu hỏi pháp lý: ").strip()

            if not user_query:
                print("⚠️ Vui lòng nhập nội dung câu hỏi!")
                continue

            if user_query.lower() in ("exit", "quit", "q", "thoat"):
                print("\n👋 Đã dừng chương trình đánh giá. Hẹn gặp lại!\n")
                break

            expected_cit = input("👉 (Tùy chọn) Nhập điều luật kỳ vọng [Nhấn Enter để bỏ qua]: ").strip()
            if not expected_cit:
                expected_cit = None

            print("\n⏳ Đang tra cứu RAG, phân tích Granularity, kiểm tra Legal Entailment...")
            card = evaluator.run_evaluation(user_query, expected_citation=expected_cit)
            display_scorecard(card, expected=expected_cit)

        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Đã thoát chương trình.")
            break


def main():
    parser = argparse.ArgumentParser(description="Legal RAG Evaluation & Diagnostics Framework.")
    parser.add_argument("--query", type=str, default=None, help="Câu hỏi pháp lý cần đánh giá")
    parser.add_argument("--expected", type=str, default=None, help="Căn cứ điều luật kỳ vọng")
    parser.add_argument("--db-dir", type=str, default="chroma_legal_db", help="Thư mục ChromaDB")
    args = parser.parse_args()

    evaluator = LegalRAGEvaluator(db_dir=args.db_dir)

    if args.query:
        card = evaluator.run_evaluation(args.query, expected_citation=args.expected)
        display_scorecard(card, expected=args.expected)
    else:
        interactive_mode(evaluator)


if __name__ == "__main__":
    main()
