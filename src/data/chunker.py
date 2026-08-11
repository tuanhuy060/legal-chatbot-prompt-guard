"""
Module phân đoạn (chunking) văn bản pháp luật theo cấu trúc Điều/Khoản.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langchain_text_splitters import RecursiveCharacterTextSplitter

# Cấu hình Recursive splitter cho những "Điều" quá dài
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    separators=["\n\n", "\n", ".", " ", ""]
)


def create_context_header(metadata: dict[str, Any]) -> str:
    """Tạo đoạn text bối cảnh để gắn vào đầu mỗi chunk."""
    title = metadata.get("title", "")
    so_ky_hieu = metadata.get("so_ky_hieu", "")
    co_quan = metadata.get("co_quan_ban_hanh", "")
    ngay = metadata.get("ngay_ban_hanh", "")
    pham_vi = metadata.get("pham_vi", "")

    header = (
        f"[BỐI CẢNH VĂN BẢN]\n"
        f"Tên văn bản: {title}\n"
        f"Số ký hiệu: {so_ky_hieu} | Cơ quan ban hành: {co_quan} | Ngày ban hành: {ngay} | Phạm vi áp dụng: {pham_vi}\n"
        f"---\n"
    )
    return header


def chunk_legal_document(doc_json: dict[str, Any], min_length: int = 150, max_length: int = 1500) -> list[dict[str, Any]]:
    """Phân đoạn một văn bản pháp luật theo từng Điều, gom chunk ngắn và cắt nhỏ chunk dài."""
    content = doc_json.get("content_clean", "")
    metadata = doc_json.get("metadata", {})
    doc_id = doc_json.get("id", "")

    if not content:
        return []

    context_header = create_context_header(metadata)
    chunks: list[dict[str, Any]] = []

    # 1. Tách văn bản theo "Điều X." hoặc "Điều X:"
    parts = re.split(r'\n(Điều \d+[\.\:])', content)

    # Phần mở đầu trước Điều 1 (Căn cứ & Tiêu đề)
    intro_text = parts[0].strip()
    if intro_text:
        chunk_text = context_header + "[Phần Căn cứ & Lời mở đầu]\n" + intro_text
        chunks.append({
            "doc_id": doc_id,
            "chunk_content": chunk_text,
            "metadata": metadata
        })

    # 2. Ghép từng Điều lại với nội dung
    for i in range(1, len(parts), 2):
        dieu_title = parts[i].strip()
        dieu_content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        full_dieu_text = f"{dieu_title} {dieu_content}"

        # Gom chunk ngắn vào chunk liền trước nếu < min_length
        if len(full_dieu_text) < min_length and len(chunks) > 0:
            last_chunk = chunks.pop()
            last_chunk["chunk_content"] += "\n\n" + full_dieu_text
            chunks.append(last_chunk)
            continue

        chunk_text = context_header + full_dieu_text

        # Cắt nhỏ nếu Điều quá dài (> max_length)
        if len(chunk_text) > max_length:
            sub_chunks = text_splitter.split_text(full_dieu_text)
            for j, sub in enumerate(sub_chunks):
                sub_chunk_text = context_header + f"[{dieu_title} - Phần {j+1}]\n" + sub
                chunks.append({
                    "doc_id": doc_id,
                    "chunk_content": sub_chunk_text,
                    "metadata": metadata
                })
        else:
            chunks.append({
                "doc_id": doc_id,
                "chunk_content": chunk_text,
                "metadata": metadata
            })

    return chunks


def process_chunking(input_path: Path, output_path: Path) -> int:
    """Xử lý chunking toàn bộ file JSONL và ghi ra file kết quả."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {input_path.resolve()}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Đang đọc dữ liệu từ file: {input_path}...")
    total_chunks = 0
    total_docs = 0

    with (
        input_path.open("r", encoding="utf-8") as in_f,
        output_path.open("w", encoding="utf-8") as out_f
    ):
        for line in in_f:
            if not line.strip():
                continue
            total_docs += 1
            doc_json = json.loads(line)
            doc_chunks = chunk_legal_document(doc_json)
            for chunk in doc_chunks:
                out_f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                total_chunks += 1

            if total_docs % 5000 == 0:
                print(f"  Đã xử lý {total_docs:,} văn bản -> {total_chunks:,} chunks...")

    print(f"\nHoàn tất! Đã xử lý {total_docs:,} văn bản -> tạo ra {total_chunks:,} chunks.")
    print(f"Kết quả được lưu tại: {output_path.resolve()}")
    return total_chunks


def main():
    parser = argparse.ArgumentParser(description="Phân đoạn văn bản pháp luật thành các chunks phục vụ RAG.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/vietnamese_legal_active_clean.jsonl"), help="File JSONL đã làm sạch")
    parser.add_argument("--output", type=Path, default=Path("data/processed/chunked.jsonl"), help="File JSONL sau khi chunking")

    args = parser.parse_args()
    process_chunking(args.input, args.output)


if __name__ == "__main__":
    main()
