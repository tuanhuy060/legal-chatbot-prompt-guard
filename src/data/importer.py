"""
Module Trích xuất & Làm sạch Dữ liệu Pháp luật từ Kho Parquet (171k văn bản) sang JSONL.
Ưu tiên hàng đầu các Bộ luật, Luật và Nghị định Trọng điểm Quốc gia CÒN HIỆU LỰC.
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

PARQUET_DIR = Path("data/raw")
OUTPUT_CLEAN = Path("data/processed/vietnamese_legal_active_clean.jsonl")

# Danh sách từ khóa các Văn bản Luật Trọng điểm Quốc gia bắt buộc phải có
PRIORITY_KEYWORDS = [
    "Doanh nghiệp",
    "Dân sự",
    "Lao động",
    "Đầu tư",
    "Thương mại",
    "Hình sự",
    "Đất đai",
    "Giao thông đường bộ",
    "Trật tự, an toàn giao thông đường bộ",
    "Nhà ở",
    "Kinh doanh bất động sản",
    "Thuế thu nhập cá nhân",
    "Thuế thu nhập doanh nghiệp",
    "Thuế giá trị gia tăng",
    "Xử lý vi phạm hành chính",
    "Bảo hiểm xã hội",
    "An ninh mạng",
    "Sở hữu trí tuệ",
    "Quản lý thuế"
]


def clean_html_content(raw_html: str) -> str:
    """Loại bỏ thẻ HTML rác và chuẩn hóa văn bản tiếng Việt Unicode."""
    if not raw_html or not isinstance(raw_html, str):
        return ""

    decoded = html.unescape(raw_html)
    soup = BeautifulSoup(decoded, "html.parser")
    for br in soup.find_all(["br", "p", "div", "tr", "li"]):
        br.append("\n")

    text = soup.get_text()
    text = unicodedata.normalize("NFC", text)

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


def parse_date_safe(date_str: Any) -> pd.Timestamp:
    """Chuyển đổi chuỗi ngày ban hành DD/MM/YYYY thành Timestamp chuẩn để sắp xếp."""
    if not date_str or not isinstance(date_str, str):
        return pd.Timestamp("1970-01-01")
    try:
        parts = date_str.strip().split("/")
        if len(parts) == 3:
            return pd.Timestamp(year=int(parts[2]), month=int(parts[1]), day=int(parts[0]))
    except Exception:
        pass
    return pd.Timestamp("1970-01-01")


# Danh sách ID và Số ký hiệu các Văn bản Luật Cốt lõi Quốc gia BẮT BUỘC PHẢI CÓ
CORE_LAW_PINNED_IDS = {
    "142881": "Luật Doanh nghiệp số 59/2020/QH14",
    "95942": "Bộ luật Dân sự số 91/2015/QH13",
    "139264": "Bộ luật Lao động số 45/2019/QH14",
    "179095": "Luật Sửa đổi, bổ sung một số điều của Luật Doanh nghiệp số 76/2025/QH15",
}

CORE_LAW_SYMBOLS = [
    "59/2020/QH14",
    "91/2015/QH13",
    "45/2019/QH14",
    "76/2025/QH15",
    "61/2020/QH14",
    "31/2024/QH15",
    "27/2023/QH15",
    "29/2023/QH15",
    "36/2024/QH15",
    "100/2015/QH13",
    "15/2012/QH13",
    "24/2018/QH14",
    "41/2024/QH15",
    "67/2025/QH15",
    "48/2024/QH15",
]


def is_priority_doc(title: str, symbol: str, doc_id: str) -> bool:
    """Kiểm tra xem văn bản có thuộc nhóm luật trọng điểm hay không."""
    if str(doc_id) in CORE_LAW_PINNED_IDS:
        return True
    if any(s in str(symbol) for s in CORE_LAW_SYMBOLS):
        return True
    if not title:
        return False
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in PRIORITY_KEYWORDS)


def extract_active_laws(
    parquet_dir: Path = PARQUET_DIR,
    output_path: Path = OUTPUT_CLEAN,
    limit_docs: int = 500
) -> int:
    """Trích xuất và làm sạch các văn bản luật cốt lõi còn hiệu lực."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    meta_file = parquet_dir / "metadata.parquet"
    content_file = parquet_dir / "content.parquet"

    print(f"[Importer] Đang đọc metadata từ: {meta_file}...")
    df_meta = pd.read_parquet(meta_file)

    # 1. Lọc văn bản còn hiệu lực hoặc hết hiệu lực 1 phần
    valid_status = ["Còn hiệu lực", "Hết hiệu lực một phần"]
    active_meta = df_meta[df_meta["tinh_trang_hieu_luc"].isin(valid_status)].copy()

    # Ghim các ID cốt lõi
    df_meta_pinned = df_meta[df_meta["id"].isin(list(CORE_LAW_PINNED_IDS.keys()))].copy()
    active_meta = pd.concat([df_meta_pinned, active_meta]).drop_duplicates(subset=["id"])
    print(f"[Importer] Tổng số văn bản Còn hiệu lực / Hết hiệu lực 1 phần: {len(active_meta):,}")

    # 2. Lọc các loại văn bản quy phạm pháp luật cốt lõi
    target_types = ["Bộ luật", "Luật", "Nghị định", "Nghị quyết", "Thông tư"]
    core_meta = active_meta[active_meta["loai_van_ban"].isin(target_types)].copy()

    # 3. Phân cấp ưu tiên thông minh
    core_meta["parsed_date"] = core_meta["ngay_ban_hanh"].apply(parse_date_safe)
    core_meta["is_pinned"] = core_meta["id"].apply(lambda x: str(x) in CORE_LAW_PINNED_IDS)
    core_meta["is_priority"] = core_meta.apply(
        lambda r: is_priority_doc(r.get("title", ""), r.get("so_ky_hieu", ""), r.get("id", "")),
        axis=1
    )

    type_ranks = {"Bộ luật": 1, "Luật": 2, "Nghị định": 3, "Nghị quyết": 4, "Thông tư": 5}
    core_meta["type_rank"] = core_meta["loai_van_ban"].map(lambda x: type_ranks.get(x, 99))

    # Sắp xếp ưu tiên:
    # 1. Ghim các Bộ luật / Luật Trụ cột (Luật Doanh nghiệp 59/2020, Bộ luật Dân sự 91/2015...) lên số 1 tuyệt đối
    # 2. Các luật trọng điểm quốc gia
    # 3. Thứ bậc văn bản (Bộ luật -> Luật -> Nghị định)
    # 4. Ngày ban hành mới nhất
    core_meta = core_meta.sort_values(
        by=["is_pinned", "is_priority", "type_rank", "parsed_date"],
        ascending=[False, False, True, False]
    )

    if limit_docs:
        core_meta = core_meta.head(limit_docs)

    target_ids = set(core_meta["id"].tolist())
    print(f"[Importer] Đã chọn {len(target_ids):,} văn bản cốt lõi (Đã ghim trọn vẹn Luật Doanh nghiệp 59/2020, Dân sự 91/2015, Lao động 45/2019).")


    # 4. Đọc nội dung HTML và làm sạch
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

            title_val = str(row.get("title", "")).strip()
            if str(doc_id) in CORE_LAW_PINNED_IDS:
                title_val = CORE_LAW_PINNED_IDS[str(doc_id)]
            elif not title_val.startswith(("Luật", "Bộ luật", "Nghị định", "Thông tư", "Nghị quyết")):
                loai = str(row.get("loai_van_ban", "")).strip()
                if loai:
                    title_val = f"{loai} {title_val}"

            meta = {
                "title": title_val,
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
                "tinh_trang_hieu_luc": str(row.get("tinh_trang_hieu_luc", "Còn hiệu lực")).strip()
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
    extract_active_laws(limit_docs=600)
