"""
Module Trích xuất & Làm sạch Dữ liệu Pháp luật từ Kho Parquet (171k văn bản) sang JSONL.
Lọc các Văn bản Luật, Bộ luật, Nghị định CÒN HIỆU LỰC để nạp vào hệ thống RAG.
"""
import html
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from bs4 import BeautifulSoup

PARQUET_DIR = Path(r"c:\Users\tuanh\Downloads\dataset chatbot guard\vietnamese_legal_docs\data")
OUTPUT_CLEAN = Path("data/processed/vietnamese_legal_active_clean.jsonl")


def clean_html_content(raw_html: str) -> str:
    """Loại bỏ thẻ HTML rác và chuẩn hóa văn bản tiếng Việt Unicode."""
    if not raw_html or not isinstance(raw_html, str):
        return ""

    # Giải mã HTML entities
    decoded = html.unescape(raw_html)

    # Dùng BeautifulSoup để bóc tách text giữ cấu trúc xuống dòng
    soup = BeautifulSoup(decoded, "html.parser")
    for br in soup.find_all(["br", "p", "div", "tr", "li"]):
        br.append("\n")

    text = soup.get_text()

    # Chuẩn hóa Unicode NFC
    text = unicodedata.normalize("NFC", text)

    # Chuẩn hóa khoảng trắng & ngắt dòng
    lines = [line.strip() for line in text.split("\n")]
    cleaned_lines = []
    prev_empty = False

    for line in lines:
        if line:
            cleaned_lines.append(line)
            prev_empty = False
        elif not prev_empty:
            cleaned_lines.append("")
            prev_empty = True

    return "\n".join(cleaned_lines).strip()


def extract_active_laws(
    parquet_dir: Path = PARQUET_DIR,
    output_path: Path = OUTPUT_CLEAN,
    limit_docs: int | None = None
) -> int:
    """Trích xuất các văn bản Luật, Bộ luật, Nghị định còn hiệu lực."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    meta_file = parquet_dir / "metadata.parquet"
    content_file = parquet_dir / "content.parquet"

    print(f"[Importer] Đang đọc metadata từ: {meta_file}...")
    df_meta = pd.read_parquet(meta_file)

    # Lọc văn bản còn hiệu lực
    active_meta = df_meta[df_meta["tinh_trang_hieu_luc"] == "Còn hiệu lực"].copy()
    print(f"[Importer] Tổng số văn bản Còn hiệu lực: {len(active_meta):,}")

    # Ưu tiên các loại văn bản quy phạm pháp luật cốt lõi
    target_types = ["Bộ luật", "Luật", "Nghị định", "Nghị quyết", "Thông tư"]
    core_meta = active_meta[active_meta["loai_van_ban"].isin(target_types)].copy()
    
    # Sắp xếp ưu tiên: Bộ luật > Luật > Nghị định
    type_priority = {"Bộ luật": 1, "Luật": 2, "Nghị định": 3, "Nghị quyết": 4, "Thông tư": 5}
    core_meta["priority"] = core_meta["loai_van_ban"].map(lambda x: type_priority.get(x, 99))
    core_meta = core_meta.sort_values(by=["priority", "ngay_ban_hanh"], ascending=[True, False])

    if limit_docs:
        core_meta = core_meta.head(limit_docs)

    target_ids = set(core_meta["id"].tolist())
    print(f"[Importer] Đã chọn {len(target_ids):,} văn bản cốt lõi để nạp vào hệ thống.")

    # Đọc content parquet
    print(f"[Importer] Đang đọc nội dung từ: {content_file}...")
    df_content = pd.read_parquet(content_file)
    content_dict = dict(zip(df_content["id"], df_content["content_html"]))

    print(f"[Importer] Đang làm sạch và ghi ra file: {output_path}...")
    count = 0

    with output_path.open("w", encoding="utf-8") as f_out:
        for _, row in core_meta.iterrows():
            doc_id = row["id"]
            raw_html = content_dict.get(doc_id, "")
            if not raw_html or len(raw_html.strip()) < 50:
                continue

            cleaned_text = clean_html_content(raw_html)
            if len(cleaned_text) < 50:
                continue

            # Metadata tinh gọn chuẩn RAG
            meta = {
                "title": str(row.get("title", "")).strip(),
                "so_ky_hieu": str(row.get("so_ky_hieu", "")).strip(),
                "ngay_ban_hanh": str(row.get("ngay_ban_hanh", "")).strip(),
                "loai_van_ban": str(row.get("loai_van_ban", "")).strip(),
                "ngay_co_hieu_luc": str(row.get("ngay_co_hieu_luc", "")).strip(),
                "nguon_thu_thap": str(row.get("nguon_thu_thap", "")).strip(),
                "ngay_dang_cong_bao": str(row.get("ngay_dang_cong_bao", "")).strip(),
                "nganh": str(row.get("nganh", "")).strip(),
                "linh_vuc": str(row.get("linh_vuc", "")).strip(),
                "co_quan_ban_hanh": str(row.get("co_quan_ban_hanh", "")).strip(),
                "chuc_danh": str(row.get("chuc_danh", "")).strip(),
                "nguoi_ky": str(row.get("nguoi_ky", "")).strip(),
                "pham_vi": str(row.get("pham_vi", "")).strip(),
                "thong_tin_ap_dung": str(row.get("thong_tin_ap_dung", "")).strip(),
                "tinh_trang_hieu_luc": "Còn hiệu lực"
            }

            doc_entry = {
                "id": str(doc_id),
                "metadata": meta,
                "content_clean": cleaned_text
            }

            f_out.write(json.dumps(doc_entry, ensure_ascii=False) + "\n")
            count += 1

            if count % 200 == 0:
                print(f"  Đã xử lý {count:,} văn bản...")

    print(f"\n[Importer - Hoàn tất] Đã trích xuất thành công {count:,} văn bản pháp luật vào {output_path.resolve()}")
    return count


if __name__ == "__main__":
    # Trích xuất toàn bộ Bộ luật & Luật + các Nghị định trọng điểm
    extract_active_laws(limit_docs=500)
