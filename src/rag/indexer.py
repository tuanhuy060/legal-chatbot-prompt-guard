"""
Module nạp và nhúng dữ liệu vector vào ChromaDB sử dụng mô hình BAAI/bge-m3.
"""
import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Tự động trỏ cache HuggingFace sang ổ D (nếu có) để tránh đầy ổ C
if "HF_HOME" not in os.environ and Path("D:/").exists():
    os.environ["HF_HOME"] = "D:/hf_cache"

import torch
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings


def index_documents(
    input_file: Path,
    db_dir: Path,
    model_name: str = "BAAI/bge-m3",
    batch_size: int = 5000,
    collection_name: str = "legal_documents",
) -> None:
    """Nạp file chunked JSONL và lưu vào ChromaDB với cơ chế tự động chạy tiếp (auto-resume)."""
    input_file = Path(input_file)
    db_dir = Path(db_dir)

    if not input_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {input_file.resolve()}")

    # Cấu hình bộ nhớ CUDA nếu dùng GPU
    if torch.cuda.is_available():
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        device = "cuda"
        print(f"[Indexer] Sử dụng GPU: {torch.cuda.get_device_name(0)}")
    else:
        device = "cpu"
        print("[Indexer] GPU không khả dụng, sử dụng CPU.")

    print(f"[Indexer] Đang khởi tạo mô hình embedding: {model_name}...")
    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
        encode_kwargs={
            "normalize_embeddings": True,
            "batch_size": 8 if device == "cuda" else 4,
        }
    )

    print(f"[Indexer] Kết nối ChromaDB tại: {db_dir.resolve()}...")
    vector_store = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=str(db_dir)
    )

    # Tính năng Auto-Resume
    existing_count = vector_store._collection.count()
    print(f"-> Đã có sẵn {existing_count:,} chunks trong Database.")
    if existing_count > 0:
        print(f"-> Sẽ bỏ qua {existing_count:,} dòng đầu tiên trong file và tiếp tục nhúng...")

    start_time = time.time()
    documents_batch: list[Document] = []
    total_processed = existing_count

    print("[Indexer] Bắt đầu nhúng và lưu trữ...")
    with input_file.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f):
            if line_num < existing_count:
                continue

            if not line.strip():
                continue

            item = json.loads(line)
            doc = Document(
                page_content=item["chunk_content"],
                metadata=item.get("metadata", {})
            )
            documents_batch.append(doc)

            if len(documents_batch) >= batch_size:
                vector_store.add_documents(documents_batch)
                total_processed += len(documents_batch)

                elapsed_time = time.time() - start_time
                speed = len(documents_batch) / (elapsed_time if elapsed_time > 0 else 1)
                print(f"  Đã lưu: {total_processed:,} chunks | Tốc độ: {speed:.2f} chunks/s")

                start_time = time.time()
                documents_batch.clear()
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    # Xử lý nốt các document còn lại
    if documents_batch:
        vector_store.add_documents(documents_batch)
        total_processed += len(documents_batch)
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    print("\n" + "=" * 60)
    print(f"HOÀN TẤT! Tổng cộng {total_processed:,} chunks đã nằm trong ChromaDB.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Tạo vector database ChromaDB cho dữ liệu pháp luật.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/chunked.jsonl"), help="File JSONL đã phân đoạn")
    parser.add_argument("--db-dir", type=Path, default=Path("chroma_legal_db"), help="Thư mục lưu trữ ChromaDB")
    parser.add_argument("--batch-size", type=int, default=5000, help="Kích thước lô lưu DB")
    parser.add_argument("--model", type=str, default="BAAI/bge-m3", help="Tên mô hình embedding trên HuggingFace")

    args = parser.parse_args()
    index_documents(
        input_file=args.input,
        db_dir=args.db_dir,
        model_name=args.model,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
