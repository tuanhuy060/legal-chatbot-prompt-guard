"""
Module nạp và nhúng dữ liệu vector vào ChromaDB sử dụng mô hình BAAI/bge-m3.
Tối ưu hóa đa nhân CPU, index toàn bộ văn bản luật với ưu tiên 4 bộ luật cốt lõi.
"""
import argparse
import gc
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

# Cấu hình unbuffered output UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

if "HF_HOME" not in os.environ and Path("D:/").exists():
    os.environ["HF_HOME"] = "D:/hf_cache"

import torch
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

# Bật tối đa số nhân CPU để tăng tốc nhúng
cpu_threads = os.cpu_count() or 8
torch.set_num_threads(cpu_threads)
torch.set_num_interop_threads(cpu_threads)

# Các ID luật cốt lõi được ưu tiên index đầu tiên
CORE_DOC_IDS = {"142881", "95942", "139264", "179095"}


def index_documents(
    input_file: Path,
    db_dir: Path,
    model_name: str = "BAAI/bge-m3",
    batch_size: int = 32,
    collection_name: str = "legal_documents",
    reset_db: bool = False,
    max_chunks_per_law: int = 120,
    core_only: bool = False,
) -> None:
    input_file = Path(input_file)
    db_dir = Path(db_dir)

    if not input_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {input_file.resolve()}")

    if reset_db and db_dir.exists():
        print(f"[Indexer] Làm sạch cơ sở dữ liệu cũ: {db_dir.resolve()}...", flush=True)
        shutil.rmtree(db_dir, ignore_errors=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(
        f"[Indexer] Khởi tạo BGE-M3 trên thiết bị: {device.upper()} "
        f"(Đa luồng CPU: {cpu_threads} nhân)...",
        flush=True,
    )

    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
        encode_kwargs={
            "normalize_embeddings": True,
            "batch_size": 32 if device == "cuda" else 16,
        },
    )

    print(f"[Indexer] Kết nối ChromaDB tại: {db_dir.resolve()}...", flush=True)
    vector_store = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=str(db_dir),
    )

    # Kiểm tra chunk đã tồn tại để bỏ qua (tránh trùng lặp khi không reset)
    existing_ids: set[str] = set()
    if not reset_db:
        try:
            existing = vector_store.get(include=[])
            existing_ids = set(existing.get("ids", []))
            if existing_ids:
                print(
                    f"[Indexer] Đã có {len(existing_ids):,} chunks trong DB, "
                    f"sẽ bỏ qua các chunk trùng.",
                    flush=True,
                )
        except Exception:
            pass

    start_time = time.time()

    # 1. Đọc toàn bộ chunks, gom theo doc_id
    print("[Indexer] Đang đọc và phân loại chunks...", flush=True)
    core_chunks: list[dict] = []
    core_count_by_id: dict[str, int] = defaultdict(int)
    other_by_law: dict[str, list[dict]] = defaultdict(list)

    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            meta = item.get("metadata", {})
            doc_id = str(meta.get("doc_id", ""))

            if doc_id in CORE_DOC_IDS:
                if core_count_by_id[doc_id] < max_chunks_per_law:
                    core_chunks.append(item)
                    core_count_by_id[doc_id] += 1
            elif not core_only:
                law_key = doc_id or meta.get("so_ky_hieu", "unknown")
                if len(other_by_law[law_key]) < max_chunks_per_law:
                    other_by_law[law_key].append(item)

    # 2. Gộp: core trước, các luật khác sau
    other_chunks = [chunk for chunks in other_by_law.values() for chunk in chunks]
    selected_chunks = core_chunks + other_chunks

    print(
        f"[Indexer] Đã chọn {len(selected_chunks):,} chunks "
        f"từ {len(core_count_by_id) + len(other_by_law)} văn bản:",
        flush=True,
    )
    for doc_id, cnt in core_count_by_id.items():
        print(f"  - [Core] doc_id={doc_id}: {cnt} chunks", flush=True)
    if not core_only:
        print(
            f"  - Các luật khác ({len(other_by_law)} văn bản): {len(other_chunks):,} chunks",
            flush=True,
        )

    # 3. Nhúng và lưu theo batch
    batch_docs: list[Document] = []
    batch_ids: list[str] = []
    total_processed = 0
    skipped = 0

    for item in selected_chunks:
        cid = item.get("chunk_id")
        content = item.get("chunk_content", "")
        meta = item.get("metadata", {})

        if not content or not cid:
            continue

        # Bỏ qua nếu đã tồn tại trong DB
        if cid in existing_ids:
            skipped += 1
            continue

        batch_docs.append(Document(page_content=content, metadata=meta))
        batch_ids.append(cid)

        if len(batch_docs) >= batch_size:
            vector_store.add_documents(documents=batch_docs, ids=batch_ids)
            total_processed += len(batch_docs)

            elapsed = time.time() - start_time
            speed = total_processed / (elapsed if elapsed > 0 else 1)
            remaining = len(selected_chunks) - total_processed - skipped
            eta = remaining / speed if speed > 0 else 0
            print(
                f"  -> Đã nhúng & lưu: {total_processed:,} / ~{len(selected_chunks):,} chunks "
                f"({speed:.1f} chunks/s | ETA: {eta / 60:.1f} phút)",
                flush=True,
            )

            batch_docs.clear()
            batch_ids.clear()
            gc.collect()

    if batch_docs:
        vector_store.add_documents(documents=batch_docs, ids=batch_ids)
        total_processed += len(batch_docs)
        gc.collect()

    elapsed_total = time.time() - start_time
    print("\n" + "=" * 70, flush=True)
    print(
        f"HOÀN TẤT TRONG {elapsed_total:.1f} GIÂY! "
        f"Đã nhúng {total_processed:,} chunks mới (bỏ qua {skipped:,} trùng).",
        flush=True,
    )
    print("=" * 70, flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Tạo vector database ChromaDB cho dữ liệu pháp luật."
    )
    parser.add_argument("--input", type=Path, default=Path("data/processed/chunked.jsonl"))
    parser.add_argument("--db-dir", type=Path, default=Path("D:/chroma_legal_db"))
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--model", type=str, default="BAAI/bge-m3")
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Xóa DB cũ trước khi index (mặc định: False — giữ lại DB cũ)",
    )
    parser.add_argument(
        "--max-per-law",
        type=int,
        default=120,
        help="Số chunk tối đa mỗi văn bản luật (mặc định: 120)",
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        default=False,
        help="Chỉ index 4 bộ luật cốt lõi, bỏ qua các luật khác",
    )

    args = parser.parse_args()
    index_documents(
        input_file=args.input,
        db_dir=args.db_dir,
        model_name=args.model,
        batch_size=args.batch_size,
        reset_db=args.reset,
        max_chunks_per_law=args.max_per_law,
        core_only=args.core_only,
    )


if __name__ == "__main__":
    main()
