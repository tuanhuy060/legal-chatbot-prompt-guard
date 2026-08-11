"""
Script kiểm thử toàn bộ Pipeline: Prompt Guard -> Vector Search -> Semantic Rerank -> Legal Score.
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


def main():
    parser = argparse.ArgumentParser(description="Kiểm thử Pipeline RAG Pháp Luật toàn diện.")
    parser.add_argument(
        "--query",
        type=str,
        default="Người dưới 18 tuổi có được thành lập doanh nghiệp không?",
        help="Câu hỏi pháp lý cần tra cứu"
    )
    parser.add_argument("--candidates-k", type=int, default=20, help="Số lượng ứng viên retrieve ban đầu")
    parser.add_argument("--top-k", type=int, default=5, help="Số kết quả trả về cuối cùng sau rerank")
    parser.add_argument("--db-dir", type=str, default="chroma_legal_db", help="Đường dẫn thư mục ChromaDB")
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print(f"CÂU HỎI TRUY VẤN: \"{args.query}\"")
    print("=" * 80)

    # 1. KIỂM DUYỆT BẢO MẬT (PROMPT GUARD)
    print("\n[Bước 1] Kiểm tra an toàn đầu vào (Prompt Guard)...")
    guard = PromptGuard()
    guard_res = guard.inspect(args.query)
    print(f"  -> Trạng thái: {guard_res.risk_level.value.upper()} (Risk score: {guard_res.risk_score})")
    print(f"  -> Thông báo: {guard_res.message}")

    if not guard_res.is_safe:
        print("\n[CẢNH BÁO] Câu truy vấn bị chặn do phát hiện nguy cơ tấn công injection!")
        return

    # 2. VECTOR RETRIEVAL (BGE-M3 + ChromaDB)
    print(f"\n[Bước 2] Tìm kiếm Vector Top {args.candidates_k} ứng viên...")
    retriever = LegalRetriever(db_dir=args.db_dir)
    candidates = retriever.retrieve(args.query, k=args.candidates_k)

    if not candidates:
        print("  -> Không tìm thấy văn bản phù hợp trong Database.")
        return

    print(f"  -> Đã tìm thấy {len(candidates)} ứng viên.")

    # 3. SEMANTIC RERANK (bge-reranker-v2-m3)
    print(f"\n[Bước 3] Tái xếp hạng ngữ nghĩa (Semantic Cross-Encoder)...")
    reranker = LegalReranker()
    reranked = reranker.rerank(args.query, candidates, top_k=args.candidates_k)

    # 4. LEGAL SPECIALIZED RANKING
    print(f"\n[Bước 4] Áp dụng xếp hạng Pháp lý chuyên sâu (Độ mới + Thứ bậc văn bản)...")
    final_results = legal_rerank(reranked, top_k=args.top_k)

    # 5. HIỂN THỊ KẾT QUẢ TOP K
    print("\n" + "=" * 80)
    print(f"TOP {len(final_results)} VĂN BẢN PHÁP LUẬT PHÙ HỢP NHẤT")
    print("=" * 80)

    for i, item in enumerate(final_results, 1):
        doc = item["document"]
        meta = doc.metadata
        print(f"\n[{i}] ĐIỂM TỔNG HỢP: {item.get('legal_final_score', 0):.4f}")
        print(f"    - Điểm Ngữ nghĩa (Reranker): {item.get('reranker_score', 0):.4f}")
        print(f"    - Điểm Độ mới (Recency):     {item.get('recency_score', 0):.4f}")
        print(f"    - Điểm Thứ bậc (Type):       {item.get('legal_type_score', 0):.4f}")
        print(f"    - Tên văn bản:               {meta.get('title', 'N/A')}")
        print(f"    - Loại văn bản:              {meta.get('loai_van_ban', 'N/A')}")
        print(f"    - Số ký hiệu:                {meta.get('so_ky_hieu', 'N/A')}")
        print(f"    - Ngày có hiệu lực:          {meta.get('ngay_co_hieu_luc', 'N/A')}")
        print(f"    - Trích đoạn nội dung:\n{doc.page_content[:450]}...")
        print("-" * 80)


if __name__ == "__main__":
    main()
