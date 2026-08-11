"""
Module Phân đoạn (Chunking) Văn bản Pháp luật Chuẩn Ngữ Cảnh (Context-Preserving Chunker).
Bảo đảm mọi sub-chunk đều kế thừa đầy đủ Tiêu đề Văn bản + Tiêu đề Điều + Mệnh đề Khoản mẹ.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def create_context_header(metadata: dict[str, Any]) -> str:
    """Tạo tiêu đề bối cảnh văn bản chuẩn."""
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


def split_dieu_by_khoan(dieu_title_line: str, dieu_body: str, max_length: int = 900) -> list[str]:
    """Chia nhỏ một Điều dài theo từng Khoản, giữ nguyên tiêu đề Điều ở đầu mỗi đoạn."""
    # Tìm các Khoản: "1. ", "2. ", "3. "...
    khoan_parts = re.split(r'\n(?=\d+\.\s+)', "\n" + dieu_body.strip())
    
    sub_chunks = []
    current_chunk = ""

    for part in khoan_parts:
        part = part.strip()
        if not part:
            continue

        candidate = f"{current_chunk}\n\n{part}".strip() if current_chunk else part

        if len(candidate) <= max_length:
            current_chunk = candidate
        else:
            if current_chunk:
                # Đóng gói chunk trước đó kèm Tiêu đề Điều
                full_text = f"{dieu_title_line}\n{current_chunk}"
                sub_chunks.append(full_text)
            current_chunk = part

    if current_chunk:
        full_text = f"{dieu_title_line}\n{current_chunk}"
        sub_chunks.append(full_text)

    # Nếu Điều không có cấu trúc Khoản rõ ràng mà vẫn dài quá max_length
    if not sub_chunks:
        lines = [l.strip() for l in dieu_body.split("\n") if l.strip()]
        cur = ""
        for line in lines:
            if len(cur) + len(line) + 1 <= max_length:
                cur = f"{cur}\n{line}".strip() if cur else line
            else:
                if cur:
                    sub_chunks.append(f"{dieu_title_line}\n{cur}")
                cur = line
        if cur:
            sub_chunks.append(f"{dieu_title_line}\n{cur}")

    return sub_chunks if sub_chunks else [f"{dieu_title_line}\n{dieu_body}"]


def chunk_legal_document(
    doc_json: dict[str, Any],
    min_length: int = 100,
    max_length: int = 1100
) -> list[dict[str, Any]]:
    """Phân đoạn văn bản pháp luật theo cấu trúc Điều/Khoản kế thừa ngữ cảnh."""
    content = doc_json.get("content_clean", "")
    metadata = doc_json.get("metadata", {})
    doc_id = str(doc_json.get("id", ""))

    if not content:
        return []

    context_header = create_context_header(metadata)
    chunks: list[dict[str, Any]] = []

    # 1. Tách văn bản theo "Điều X." hoặc "Điều X:"
    parts = re.split(r'\n(?=Điều\s+\d+[\.\:])', content)

    # Phần mở đầu trước Điều 1 (Căn cứ & Tiêu đề)
    if parts and not parts[0].strip().startswith("Điều"):
        intro_text = parts[0].strip()
        if len(intro_text) >= 50:
            chunks.append({
                "doc_id": doc_id,
                "chunk_content": f"{context_header}[Phần Căn cứ & Lời mở đầu]\n{intro_text}",
                "metadata": metadata
            })
        parts = parts[1:]

    # 2. Xử lý từng Điều
    for part in parts:
        part_text = part.strip()
        if not part_text:
            continue

        # Tách dòng đầu (Tiêu đề Điều) và phần thân
        lines = part_text.split("\n", 1)
        dieu_title = lines[0].strip()
        dieu_body = lines[1].strip() if len(lines) > 1 else ""

        full_dieu_text = f"{dieu_title}\n{dieu_body}".strip()

        # Nếu độ dài vừa vặn -> Giữ nguyên 1 chunk hoàn chỉnh
        if len(full_dieu_text) <= max_length:
            chunk_text = f"{context_header}{full_dieu_text}"
            chunks.append({
                "doc_id": doc_id,
                "chunk_content": chunk_text,
                "metadata": metadata
            })
        else:
            # Nếu Điều quá dài -> Chia theo Khoản nhưng LUÔN KẾ THỪA TIÊU ĐỀ ĐIỀU
            sub_dieu_chunks = split_dieu_by_khoan(dieu_title, dieu_body, max_length=max_length - len(context_header))
            for sub in sub_dieu_chunks:
                chunks.append({
                    "doc_id": doc_id,
                    "chunk_content": f"{context_header}{sub}",
                    "metadata": metadata
                })

    return chunks


def process_chunking(input_path: Path, output_path: Path) -> int:
    """Xử lý chunking toàn bộ file JSONL."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {input_path.resolve()}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[Chunker] Đang đọc dữ liệu từ: {input_path}...")
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

            if total_docs % 100 == 0:
                print(f"  Đã xử lý {total_docs:,} văn bản -> {total_chunks:,} chunks...")

    print(f"\n[Chunker - Hoàn tất] Đã xử lý {total_docs:,} văn bản -> tạo ra {total_chunks:,} chunks chất lượng cao.")
    print(f"Kết quả lưu tại: {output_path.resolve()}")
    return total_chunks


def main():
    parser = argparse.ArgumentParser(description="Phân đoạn văn bản pháp luật kế thừa ngữ cảnh.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/vietnamese_legal_active_clean.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/chunked.jsonl"))

    args = parser.parse_args()
    process_chunking(args.input, args.output)


if __name__ == "__main__":
    main()
