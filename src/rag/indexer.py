"""
Module nạp và nhúng dữ liệu vector vào ChromaDB sử dụng mô hình BAAI/bge-m3.
Tối ưu hóa tốc độ nhúng đa luồng và hỗ trợ tái lập chỉ mục sạch (Clean Reset).
"""
import argparse
import gc
import json
import os
import shutil
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
    batch_size: int = 200,
    collection_name: str = "legal_documents",
    reset_db: bool = False,
    max_chunks: int | None = None
) -> None:
    """Nạp file chunked JSONL và lưu vào ChromaDB."""
    input_file = Path(input_file)
    db_dir = Path(db_dir)

    if not input_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {input_file.resolve()}")

    if reset_db and db_dir.exists():
        print(f"[Indexer] Đang dọn dẹp cơ sở dữ liệu cũ tại: {db_dir.resolve()}...")
        try:
            shutil.rmtree(db_dir)
        except Exception as e:
            print(f"[Indexer - Cảnh báo] Không thể xóa thư mục cũ: {e}")

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
            "batch_size": 16 if device == "cuda" else 8,
        }
    )

    print(f"[Indexer] Kết nối ChromaDB tại: {db_dir.resolve()}...")
    vector_store = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=str(db_dir)
    )

    start_time = time.time()
    documents_batch: list[Document] = []
    total_processed = 0

    print("[Indexer] Bắt đầu nhúng và lưu trữ...")
    with input_file.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f):
            if max_chunks and total_processed >= max_chunks:
                break

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
                speed = total_processed / (elapsed_time if elapsed_time > 0 else 1)
                print(f"  Đã lưu: {total_processed:,} chunks | Tốc độ: {speed:.1f} chunks/s")

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
    parser.add_argument("--batch-size", type=int, default=200, help="Kích thước lô nhúng")
    parser.add_argument("--model", type=str, default="BAAI/bge-m3", help="Tên mô hình embedding")
    parser.add_argument("--reset", action="store_true", default=True, help="Xóa database cũ để tạo lại")
    parser.add_argument("--max-chunks", type=int, default=2000, help="Số chunks tối đa nạp thử nghiệm ban đầu")

    args = parser.parse_args()
    index_documents(
        input_file=args.input,
        db_dir=args.db_dir,
        model_name=args.model,
        batch_size=args.batch_size,
        reset_db=args.reset,
        max_chunks=args.max_chunks
    )


if __name__ == "__main__":
    main()
