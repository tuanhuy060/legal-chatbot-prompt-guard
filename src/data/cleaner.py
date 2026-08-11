"""
Module làm sạch HTML, chuẩn hóa Unicode tiếng Việt, nối metadata và lọc văn bản theo hiệu lực.
"""
import argparse
import csv
import html
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from bs4 import BeautifulSoup

# ============================================================
# CẤU HÌNH TRẠNG THÁI HIỆU LỰC
# ============================================================

ACTIVE_STATUSES = {
    "còn hiệu lực",
}

PARTIAL_STATUSES = {
    "hết hiệu lực một phần",
    "ngưng hiệu lực một phần",
}

EXCLUDED_STATUSES = {
    "hết hiệu lực toàn bộ",
    "ngưng hiệu lực",
    "không còn phù hợp",
    "chưa có hiệu lực",
}

# Các mẫu dòng rác thường gặp
NOISE_LINE_PATTERNS = [
    re.compile(r"^\s*trang\s*:?\s*\d+(?:\s*/\s*\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*page\s*:?\s*\d+(?:\s+of\s+\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$"),
    re.compile(r"^\s*[-–—_=*.•·]{3,}\s*$"),
    re.compile(r"^\s*(about:blank|javascript:void\(0\);?)\s*$", re.IGNORECASE),
]


# ============================================================
# HÀM CHUẨN HÓA VĂN BẢN
# ============================================================

def clean_scalar(value: Any) -> str:
    """Chuyển một giá trị metadata thành chuỗi sạch."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    text = str(value).strip()
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_id(value: Any) -> str:
    """Chuẩn hóa ID giữa file JSONL và metadata.csv."""
    doc_id = clean_scalar(value)
    if re.fullmatch(r"\d+\.0", doc_id):
        doc_id = doc_id[:-2]
    return doc_id


def normalize_status(value: Any) -> str:
    """Chuẩn hóa trạng thái để so sánh."""
    status = clean_scalar(value)
    return status.casefold()


def normalize_unicode(text: str) -> str:
    """Giải mã HTML entity, chuẩn hóa Unicode tiếng Việt (NFC) và loại bỏ ký tự ẩn."""
    if not text:
        return ""

    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u00ad", "")
    text = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", text)
    text = re.sub(r"[\u1680\u2000-\u200a\u202f\u205f\u3000]", " ", text)
    return text


def remove_control_characters(text: str) -> str:
    """Xóa ký tự điều khiển ẩn, giữ lại tab và newline."""
    return "".join(
        ch for ch in text
        if ch in {"\n", "\t"} or unicodedata.category(ch) != "Cc"
    )


def is_noise_line(line: str) -> bool:
    """Kiểm tra một dòng có phải dòng rác (số trang, đường kẻ...) hay không."""
    line = line.strip()
    if not line:
        return True
    return any(p.fullmatch(line) for p in NOISE_LINE_PATTERNS)


def normalize_line(line: str) -> str:
    """Chuẩn hóa khoảng trắng và dấu câu trong một dòng."""
    line = normalize_unicode(line)
    line = remove_control_characters(line)
    line = re.sub(r"[ \t]+", " ", line)
    line = re.sub(r"\s+([,.;:!?%)\]])", r"\1", line)
    line = re.sub(r"([(\[])\s+", r"\1", line)
    return line.strip()


def html_to_text(content_html: str) -> str:
    """Chuyển đổi nội dung HTML thành văn bản thuần sạch, giữ cấu trúc Điều/Khoản."""
    if not isinstance(content_html, str) or not content_html.strip():
        return ""

    soup = BeautifulSoup(content_html, "html.parser")

    # Xóa các tag không chứa nội dung văn bản
    for tag in soup.find_all(["script", "style", "noscript", "template", "svg", "canvas", "iframe", "form", "button"]):
        tag.decompose()

    root = soup.body if soup.body else soup

    for br_tag in root.find_all("br"):
        br_tag.replace_with("\n")

    block_tags = [
        "p", "div", "section", "article", "header", "footer",
        "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
        "blockquote", "table", "tr", "td", "th"
    ]
    for tag in list(root.find_all(block_tags)):
        tag.insert_before("\n")
        tag.insert_after("\n")

    text = root.get_text(separator=" ")
    text = normalize_unicode(text)
    text = remove_control_characters(text)

    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = normalize_line(raw_line)
        if not line or is_noise_line(line):
            continue
        if cleaned_lines and cleaned_lines[-1] == line:
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


# ============================================================
# PHÂN LOẠI HIỆU LỰC
# ============================================================

def parse_vietnamese_date(value: Any) -> date | None:
    """Đọc ngày tháng định dạng VN (dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd)."""
    text = clean_scalar(value)
    if not text or text in {"...", "-", "--"}:
        return None

    date_patterns = [
        (r"(\d{1,2}/\d{1,2}/\d{4})", "%d/%m/%Y"),
        (r"(\d{1,2}-\d{1,2}-\d{4})", "%d-%m-%Y"),
        (r"(\d{4}-\d{1,2}-\d{1,2})", "%Y-%m-%d"),
    ]

    for pattern, date_format in date_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return datetime.strptime(match.group(1), date_format).date()
            except ValueError:
                continue
    return None


def classify_document(status: str, expiry_date: date | None, current_date: date) -> tuple[str, str]:
    """Phân loại văn bản: active, partial, excluded, unknown."""
    if expiry_date is not None and expiry_date <= current_date:
        return "excluded", f"Ngày hết hiệu lực đã qua: {expiry_date.strftime('%d/%m/%Y')}"

    if status in ACTIVE_STATUSES:
        return "active", "Còn hiệu lực"
    if status in PARTIAL_STATUSES:
        return "partial", "Văn bản chỉ còn hiệu lực một phần"
    if status in EXCLUDED_STATUSES:
        return "excluded", status
    if status == "chưa xác định":
        return "unknown", "Trạng thái chưa xác định"

    return "unknown", "Thiếu trạng thái hiệu lực"


def load_metadata(metadata_path: Path) -> dict[str, dict[str, Any]]:
    """Đọc metadata.csv và trả về dictionary tra cứu theo ID."""
    dataframe = pd.read_csv(
        metadata_path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
        low_memory=False,
    )

    required_columns = {"id", "title", "tinh_trang_hieu_luc", "ngay_het_hieu_luc"}
    missing_columns = required_columns - set(dataframe.columns)
    if missing_columns:
        raise ValueError(f"metadata.csv thiếu các cột bắt buộc: {', '.join(sorted(missing_columns))}")

    metadata_by_id: dict[str, dict[str, Any]] = {}
    for _, row in dataframe.iterrows():
        doc_id = normalize_id(row.get("id"))
        if not doc_id:
            continue
        metadata_by_id[doc_id] = {col: clean_scalar(row.get(col, "")) for col in dataframe.columns}

    return metadata_by_id


def build_rag_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Trích xuất các trường metadata cần thiết cho RAG."""
    fields = [
        "title", "so_ky_hieu", "ngay_ban_hanh", "loai_van_ban",
        "ngay_co_hieu_luc", "ngay_het_hieu_luc", "nguon_thu_thap",
        "ngay_dang_cong_bao", "nganh", "linh_vuc", "co_quan_ban_hanh",
        "chuc_danh", "nguoi_ky", "pham_vi", "thong_tin_ap_dung", "tinh_trang_hieu_luc"
    ]
    return {f: clean_scalar(metadata.get(f, "")) for f in fields if clean_scalar(metadata.get(f, ""))}


def process_jsonl(
    input_path: Path,
    metadata_path: Path,
    output_dir: Path,
    remove_html: bool = True
) -> None:
    """Xử lý toàn bộ pipeline làm sạch và phân loại văn bản pháp luật."""
    input_path = Path(input_path)
    metadata_path = Path(metadata_path)
    output_dir = Path(output_dir)

    active_out = output_dir / "vietnamese_legal_active_clean.jsonl"
    partial_out = output_dir / "vietnamese_legal_partial_review.jsonl"
    unknown_out = output_dir / "vietnamese_legal_unknown_review.jsonl"
    audit_out = output_dir / "legal_filter_audit.csv"
    summary_out = output_dir / "legal_filter_summary.json"

    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file nội dung: {input_path.resolve()}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file metadata: {metadata_path.resolve()}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print("Đang đọc metadata.csv...")
    metadata_by_id = load_metadata(metadata_path)
    print(f"Đã nạp {len(metadata_by_id):,} bản ghi metadata.")

    current_date = date.today()
    counters = {
        "total_jsonl": 0, "active": 0, "partial": 0, "excluded": 0,
        "unknown": 0, "missing_metadata": 0, "invalid_json": 0,
        "empty_content": 0, "written_active": 0, "written_partial": 0, "written_unknown": 0,
    }
    audit_rows: list[dict[str, Any]] = []

    print("Đang xử lý dữ liệu JSONL...")
    with (
        input_path.open("r", encoding="utf-8-sig") as in_f,
        active_out.open("w", encoding="utf-8") as act_f,
        partial_out.open("w", encoding="utf-8") as part_f,
        unknown_out.open("w", encoding="utf-8") as unk_f,
    ):
        for line_num, raw_line in enumerate(in_f, start=1):
            line = raw_line.strip()
            if not line:
                continue

            counters["total_jsonl"] += 1
            if counters["total_jsonl"] % 10000 == 0:
                print(f"  Đã xử lý {counters['total_jsonl']:,} bản ghi...")

            try:
                record = json.loads(line)
            except json.JSONDecodeError as err:
                counters["invalid_json"] += 1
                audit_rows.append({
                    "line_number": line_num, "id": "", "classification": "invalid_json",
                    "status": "", "expiry_date": "", "content_status": "Lỗi JSON",
                    "reason": str(err), "title": ""
                })
                continue

            if not isinstance(record, dict):
                counters["invalid_json"] += 1
                continue

            doc_id = normalize_id(record.get("id"))
            content_html = record.get("content_html") or record.get("content") or record.get("text", "")
            metadata = metadata_by_id.get(doc_id)

            if metadata is None:
                counters["missing_metadata"] += 1
                counters["unknown"] += 1
                content_clean = html_to_text(content_html)
                if not content_clean:
                    counters["empty_content"] += 1
                else:
                    unk_record = {
                        "id": doc_id, "content_clean": content_clean,
                        "metadata": {}, "classification": "unknown",
                        "review_reason": "Không tìm thấy metadata"
                    }
                    if not remove_html:
                        unk_record["content_html"] = content_html
                    unk_f.write(json.dumps(unk_record, ensure_ascii=False) + "\n")
                    counters["written_unknown"] += 1
                continue

            status_display = clean_scalar(metadata.get("tinh_trang_hieu_luc", ""))
            status_key = normalize_status(status_display)
            expiry_date = parse_vietnamese_date(metadata.get("ngay_het_hieu_luc", ""))
            classification, reason = classify_document(status_key, expiry_date, current_date)

            counters[classification] += 1
            title = clean_scalar(metadata.get("title", ""))
            expiry_str = expiry_date.isoformat() if expiry_date else ""

            if classification == "excluded":
                audit_rows.append({
                    "line_number": line_num, "id": doc_id, "classification": classification,
                    "status": status_display, "expiry_date": expiry_str,
                    "content_status": "Không xử lý", "reason": reason, "title": title
                })
                continue

            content_clean = html_to_text(content_html)
            if not content_clean:
                counters["empty_content"] += 1
                audit_rows.append({
                    "line_number": line_num, "id": doc_id, "classification": classification,
                    "status": status_display, "expiry_date": expiry_str,
                    "content_status": "Nội dung rỗng", "reason": reason, "title": title
                })
                continue

            out_record: dict[str, Any] = {
                "id": doc_id,
                "content_clean": content_clean,
                "metadata": build_rag_metadata(metadata),
                "classification": classification,
            }
            if not remove_html:
                out_record["content_html"] = content_html

            if classification == "active":
                act_f.write(json.dumps(out_record, ensure_ascii=False) + "\n")
                counters["written_active"] += 1
            elif classification == "partial":
                out_record["review_reason"] = "Cần xác định điều khoản còn hiệu lực"
                part_f.write(json.dumps(out_record, ensure_ascii=False) + "\n")
                counters["written_partial"] += 1
            else:
                out_record["review_reason"] = reason
                unk_f.write(json.dumps(out_record, ensure_ascii=False) + "\n")
                counters["written_unknown"] += 1

            audit_rows.append({
                "line_number": line_num, "id": doc_id, "classification": classification,
                "status": status_display, "expiry_date": expiry_str,
                "content_status": "Đã làm sạch", "reason": reason, "title": title
            })

    # Ghi audit CSV
    audit_fieldnames = ["line_number", "id", "classification", "status", "expiry_date", "content_status", "reason", "title"]
    with audit_out.open("w", encoding="utf-8-sig", newline="") as af:
        writer = csv.DictWriter(af, fieldnames=audit_fieldnames)
        writer.writeheader()
        writer.writerows(audit_rows)

    # Ghi summary JSON
    summary = {
        "processing_date": current_date.isoformat(),
        "input_file": str(input_path),
        "metadata_file": str(metadata_path),
        "outputs": {
            "active": str(active_out),
            "partial": str(partial_out),
            "unknown": str(unknown_out),
            "audit": str(audit_out),
        },
        "statistics": counters,
    }
    with summary_out.open("w", encoding="utf-8") as sf:
        json.dump(summary, sf, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("HOÀN TẤT LỌC VÀ LÀM SẠCH DỮ LIỆU")
    print("=" * 60)
    print(f"Tổng bản ghi:             {counters['total_jsonl']:,}")
    print(f"Còn hiệu lực (RAG):       {counters['written_active']:,}")
    print(f"Hiệu lực một phần:        {counters['written_partial']:,}")
    print(f"Đã loại bỏ (hết hạn):     {counters['excluded']:,}")
    print(f"File kết quả RAG:         {active_out.resolve()}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Làm sạch HTML, chuẩn hóa Unicode và lọc văn bản pháp luật.")
    parser.add_argument("--input", type=Path, default=Path("data/raw/vietnamese_legal_content.jsonl"), help="File JSONL đầu vào")
    parser.add_argument("--metadata", type=Path, default=Path("data/raw/metadata.csv"), help="File CSV metadata")
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"), help="Thư mục đầu ra")
    parser.add_argument("--keep-html", action="store_true", help="Giữ lại thẻ HTML")

    args = parser.parse_args()
    process_jsonl(
        input_path=args.input,
        metadata_path=args.metadata,
        output_dir=args.output_dir,
        remove_html=not args.keep_html,
    )


if __name__ == "__main__":
    main()
