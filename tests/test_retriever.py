"""
Script kiểm thử riêng cho tầng Vector Search (Retriever).
"""
import argparse
import sys

# Đảm bảo in tiếng Việt chuẩn trên Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.rag.retriever import LegalRetriever


def main():
    parser = argparse.ArgumentParser(description="Kiểm thử Legal Retriever (Vector Search).")
    parser.add_argument("--query", type=str, default="Luật Doanh nghiệp 2020", help="Câu truy vấn thử nghiệm")
    parser.add_argument("--top-k", type=int, default=10, help="Số lượng ứng viên muốn lấy")
    parser.add_argument("--db-dir", type=str, default="chroma_legal_db", help="Thư mục ChromaDB")
    args = parser.parse_args()

    print(f"\n[Test Retriever] Đang khởi tạo với DB: '{args.db_dir}'...")
    retriever = LegalRetriever(db_dir=args.db_dir)

    print(f"\n[Test Retriever] Truy vấn: '{args.query}' (Top {args.top_k})\n" + "=" * 80)
    results = retriever.retrieve(args.query, k=args.top_k)

    for i, item in enumerate(results, 1):
        doc = item["document"]
        meta = doc.metadata
        print(f"\n[{i}] KHOẢNG CÁCH VECTOR: {item['vector_distance']:.4f}")
        print(f"    - Văn bản: {meta.get('title', 'N/A')}")
        print(f"    - Số hiệu: {meta.get('so_ky_hieu', 'N/A')}")
        print(f"    - Ngày hiệu lực: {meta.get('ngay_co_hieu_luc', 'N/A')}")
        print(f"    - Nội dung trích đoạn: {doc.page_content[:300]}...")
        print("-" * 80)


if __name__ == "__main__":
    main()
