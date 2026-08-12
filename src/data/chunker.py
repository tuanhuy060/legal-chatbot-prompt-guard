"""
Module Phân đoạn (Chunking) Văn bản Pháp luật Chuẩn Ngữ Cảnh (Context-Preserving Chunker).
Bảo đảm:
1. Mọi sub-chunk đều kế thừa đầy đủ Tiêu đề Văn bản + Tiêu đề Điều.
2. Không bao giờ ngắt ngang giữa chừng một Khoản luật (Toàn vẹn các điểm a, b, c, d...).
3. Gán Chunk ID duy nhất chuẩn hóa chống trùng lặp.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def create_context_header(metadata: dict[str, Any]) -> str:
    """Tạo tiêu đề bối cảnh văn bản chuẩn tinh gọn."""
    title = metadata.get("title", "").strip()
    so_ky_hieu = metadata.get("so_ky_hieu", "").strip()
    co_quan = metadata.get("co_quan_ban_hanh", "").strip()
    ngay = metadata.get("ngay_ban_hanh", "").strip()
    hieu_luc = metadata.get("tinh_trang_hieu_luc", "Còn hiệu lực").strip()

    header = (
        f"[BỐI CẢNH VĂN BẢN]\n"
        f"Tên văn bản: {title}\n"
        f"Số ký hiệu: {so_ky_hieu} | Cơ quan: {co_quan} | Ngày ban hành: {ngay} | Hiệu lực: {hieu_luc}\n"
        f"---\n"
    )
    return header


def split_dieu_by_khoan(dieu_title_line: str, dieu_body: str, max_length: int = 1800) -> list[str]:
    """Chia nhỏ Điều dài theo từng Khoản nguyên vẹn, luôn giữ Tiêu đề Điều ở đầu mỗi chunk."""
    # Tách theo từng Khoản: "1. ", "2. ", "3. "...
    khoan_parts = re.split(r'\n(?=\d+\.\s+)', "\n" + dieu_body.strip())
    khoan_parts = [p.strip() for p in khoan_parts if p.strip()]

    if not khoan_parts:
        return [f"{dieu_title_line}\n{dieu_body}".strip()]

    sub_chunks = []
    current_chunk = ""

    for part in khoan_parts:
        candidate = f"{current_chunk}\n\n{part}".strip() if current_chunk else part

        # Nếu gộp vào mà vẫn trong giới hạn max_length -> Gộp tiếp
        if len(candidate) <= max_length:
            current_chunk = candidate
        else:
            # Đóng gói chunk hiện tại kèm Header Điều
            if current_chunk:
                sub_chunks.append(f"{dieu_title_line}\n{current_chunk}".strip())
            current_chunk = part

    if current_chunk:
        sub_chunks.append(f"{dieu_title_line}\n{current_chunk}".strip())

    return sub_chunks if sub_chunks else [f"{dieu_title_line}\n{dieu_body}".strip()]


def generate_chunk_id(doc_id: str, dieu_title: str, sub_idx: int, content: str) -> str:
    """Tạo mã định danh duy nhất (Unique Chunk ID) chống trùng lặp tuyệt đối."""
    dieu_match = re.search(r'Điều\s+(\d+)', dieu_title, re.IGNORECASE)
    dieu_tag = f"D{dieu_match.group(1)}" if dieu_match else "INTRO"
    
    # Hash nội dung 8 ký tự để đảm bảo duy nhất
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
    return f"CHK_{doc_id}_{dieu_tag}_P{sub_idx}_{content_hash}"


def chunk_legal_document(
    doc_json: dict[str, Any],
    max_length: int = 2000
) -> list[dict[str, Any]]:
    """Phân đoạn văn bản pháp luật theo cấu trúc Điều/Khoản toàn vẹn ngữ cảnh."""
    content = doc_json.get("content_clean", "")
    metadata = doc_json.get("metadata", {})
    doc_id = str(doc_json.get("id", ""))

    if not content:
        return []

    context_header = create_context_header(metadata)
    chunks: list[dict[str, Any]] = []

    # 1. Tách văn bản theo "Điều X." hoặc "Điều X:"
    parts = re.split(r'\n(?=Điều\s+\d+[\.\:])', content)

    # Phần mở đầu trước Điều 1 (Căn cứ ban hành & Lời mở đầu)
    if parts and not parts[0].strip().startswith("Điều"):
        intro_text = parts[0].strip()
        if len(intro_text) >= 50:
            full_intro = f"{context_header}[Phần Căn cứ & Lời mở đầu]\n{intro_text}"
            cid = generate_chunk_id(doc_id, "Lời mở đầu", 0, full_intro)
            chunks.append({
                "chunk_id": cid,
                "doc_id": doc_id,
                "chunk_content": full_intro,
                "metadata": metadata
            })
        parts = parts[1:]

    # 2. Xử lý từng Điều luật
    for part in parts:
        part_text = part.strip()
        if not part_text:
            continue

        lines = part_text.split("\n", 1)
        dieu_title = lines[0].strip()
        dieu_body = lines[1].strip() if len(lines) > 1 else ""

        full_dieu_text = f"{dieu_title}\n{dieu_body}".strip()

        # Nếu độ dài toàn bộ Điều luật nằm trong giới hạn -> Giữ nguyên 1 chunk trọn vẹn 100%
        if len(full_dieu_text) <= max_length:
            full_chunk_text = f"{context_header}{full_dieu_text}"
            cid = generate_chunk_id(doc_id, dieu_title, 1, full_chunk_text)
            chunks.append({
                "chunk_id": cid,
                "doc_id": doc_id,
                "chunk_content": full_chunk_text,
                "metadata": metadata
            })
        else:
            # Nếu Điều quá dài -> Tách theo Khoản nhưng LUÔN KẾ THỪA TIÊU ĐỀ ĐIỀU
            sub_dieu_chunks = split_dieu_by_khoan(
                dieu_title,
                dieu_body,
                max_length=max_length - len(context_header)
            )
            for sub_idx, sub in enumerate(sub_dieu_chunks, 1):
                full_chunk_text = f"{context_header}{sub}"
                cid = generate_chunk_id(doc_id, dieu_title, sub_idx, full_chunk_text)
                chunks.append({
                    "chunk_id": cid,
                    "doc_id": doc_id,
                    "chunk_content": full_chunk_text,
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
    seen_chunk_ids = set()

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
                cid = chunk["chunk_id"]
                if cid in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(cid)

                out_f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                total_chunks += 1

            if total_docs % 100 == 0:
                print(f"  Đã xử lý {total_docs:,} văn bản -> {total_chunks:,} chunks...")

    print(f"\n[Chunker - Hoàn tất] Đã xử lý {total_docs:,} văn bản -> tạo ra {total_chunks:,} chunks toàn vẹn.")
    print(f"Kết quả lưu tại: {output_path.resolve()}")
    return total_chunks


def main():
    parser = argparse.ArgumentParser(description="Phân đoạn văn bản pháp luật kế thừa ngữ cảnh toàn vẹn.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/vietnamese_legal_active_clean.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/chunked.jsonl"))

    args = parser.parse_args()
    process_chunking(args.input, args.output)


if __name__ == "__main__":
    main()
