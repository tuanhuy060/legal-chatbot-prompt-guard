"""
Script kiểm thử toàn bộ Pipeline: Prompt Guard -> Vector Search -> Semantic Rerank -> Legal Score -> Não LLM Qwen 2.5.
Hỗ trợ cả chế độ dòng lệnh (CLI argument) và Chế độ tương tác trực tiếp (Interactive Console Box).
"""
import argparse
import sys

# Đảm bảo in tiếng Việt chuẩn trên Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.guard.prompt_guard import PromptGuard
from src.rag.retriever import LegalRetriever
from src.rag.reranker import LegalReranker
from src.rag.legal_ranker import legal_rerank
from src.rag.generator import LegalGenerator


def run_pipeline(
    query: str,
    guard: PromptGuard,
    retriever: LegalRetriever,
    reranker: LegalReranker,
    generator: LegalGenerator,
    candidates_k: int = 20,
    top_k: int = 3
):
    print("\n" + "═" * 88)
    print(f"🏛️  CÂU HỎI TRUY VẤN: \"{query}\"")
    print("═" * 88)

    # 1. KIỂM DUYỆT BẢO MẬT (PROMPT GUARD)
    print("\n[Bước 1/5] Kiểm tra an toàn đầu vào (Prompt Guard)...")
    guard_res = guard.inspect(query)
    print(f"  -> Trạng thái: {guard_res.risk_level.value.upper()} (Risk score: {guard_res.risk_score})")
    print(f"  -> Thông báo: {guard_res.message}")

    if not guard_res.is_safe:
        print("\n⛔ [CẢNH BÁO BẢO MẬT] Câu truy vấn bị CHẶN bởi Prompt Guard do phát hiện nguy cơ tấn công!")
        return

    # 2. VECTOR RETRIEVAL (BGE-M3 + ChromaDB)
    print(f"\n[Bước 2/5] Tìm kiếm Vector Top {candidates_k} ứng viên...")
    candidates = retriever.retrieve(query, k=candidates_k)

    if not candidates:
        print("  -> Không tìm thấy văn bản phù hợp trong Database.")
        return

    print(f"  -> Đã tìm thấy {len(candidates)} ứng viên.")

    # 3. SEMANTIC RERANK (bge-reranker-v2-m3)
    print(f"\n[Bước 3/5] Tái xếp hạng ngữ nghĩa (Semantic Cross-Encoder)...")
    reranked = reranker.rerank(query, candidates, top_k=candidates_k)

    # 4. LEGAL SPECIALIZED RANKING
    print(f"\n[Bước 4/5] Áp dụng xếp hạng Pháp lý chuyên sâu (Độ mới + Thứ bậc văn bản)...")
    final_results = legal_rerank(reranked, top_k=top_k)

    # Hiển thị tóm tắt căn cứ
    print(f"\n[Trích dẫn] Đã chọn lọc {len(final_results)} căn cứ pháp lý sát nhất:")
    for i, item in enumerate(final_results, 1):
        meta = item["document"].metadata or {}
        print(f"  {i}. {meta.get('title', 'Văn bản')} (Số: {meta.get('so_ky_hieu', 'N/A')}) | Điểm: {item.get('legal_final_score', 0):.4f}")

    # 5. NÃO LLM QWEN 2.5 TỔNG HỢP VÀ SUY LUẬN TRẢ LỜI
    print(f"\n[Bước 5/5] Não LLM Qwen 2.5 đang suy luận pháp lý 3 bước (CoT)...")
    answer = generator.generate_response(query, final_results)

    print("\n" + "╔" + "═" * 86 + "╗")
    print("║ 💬 CÂU TRẢ LỜI TƯ VẤN CỦA CHATBOT PHÁP LUẬT                                          ║")
    print("╚" + "═" * 86 + "╝\n")
    print(answer)
    print("\n" + "═" * 88)


def main():
    parser = argparse.ArgumentParser(description="Kiểm thử Pipeline RAG Pháp Luật toàn diện.")
    parser.add_argument("--query", type=str, default=None, help="Câu hỏi pháp lý cần tra cứu")
    parser.add_argument("--candidates-k", type=int, default=20, help="Số lượng ứng viên retrieve ban đầu")
    parser.add_argument("--top-k", type=int, default=3, help="Số kết quả chuyển vào LLM")
    parser.add_argument("--db-dir", type=str, default="chroma_legal_db", help="Đường dẫn thư mục ChromaDB")
    args = parser.parse_args()

    print("\n[Hệ thống] Đang khởi tạo các mô hình: Prompt Guard + BGE-M3 + BGE-Reranker + Qwen 2.5...")
    guard = PromptGuard()
    retriever = LegalRetriever(db_dir=args.db_dir)
    reranker = LegalReranker()
    generator = LegalGenerator()
    print("[Hệ thống] Sẵn sàng phục vụ truy vấn.\n")

    if args.query:
        run_pipeline(args.query, guard, retriever, reranker, generator, args.candidates_k, args.top_k)
    else:
        print("┌" + "─" * 86 + "┐")
        print("│                  🏛️  HỆ THỐNG TRA CỨU PHÁP LUẬT THÔNG MINH                          │")
        print("│            Nhập bất kỳ câu hỏi pháp lý nào vào ô bên dưới để tra cứu                │")
        print("│                   (Gõ 'exit' hoặc 'quit' để thoát chương trình)                     │")
        print("└" + "─" * 86 + "┘\n")

        while True:
            try:
                print("─" * 88)
                user_q = input("👉 Nhập câu hỏi pháp lý của bạn: ").strip()

                if not user_q:
                    print("⚠️ Vui lòng nhập nội dung câu hỏi!")
                    continue

                if user_q.lower() in ("exit", "quit", "q", "thoat"):
                    print("\n👋 Đã thoát hệ thống. Hẹn gặp lại!\n")
                    break

                run_pipeline(user_q, guard, retriever, reranker, generator, args.candidates_k, args.top_k)

            except (KeyboardInterrupt, EOFError):
                print("\n\n👋 Đã dừng chương trình.")
                break


if __name__ == "__main__":
    main()
