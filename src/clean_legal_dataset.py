import argparse
import csv
import html
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

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


# Những dòng văn bản rác có thể loại bỏ.
NOISE_LINE_PATTERNS = [
    # Trang 5, Trang 5/20, Trang: 5
    re.compile(
        r"^\s*trang\s*:?\s*\d+(?:\s*/\s*\d+)?\s*$",
        re.IGNORECASE,
    ),

    # Page 5, Page 5 of 20
    re.compile(
        r"^\s*page\s*:?\s*\d+(?:\s+of\s+\d+)?\s*$",
        re.IGNORECASE,
    ),

    # Dòng chỉ có số trang: 5, - 5 -, — 5 —
    re.compile(
        r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$"
    ),

    # Dòng chỉ chứa ký tự phân cách
    re.compile(
        r"^\s*[-–—_=*.•·]{3,}\s*$"
    ),

    # Một số văn bản rác do tải trang web
    re.compile(
        r"^\s*(about:blank|javascript:void\(0\);?)\s*$",
        re.IGNORECASE,
    ),
]


# ============================================================
# HÀM CHUẨN HÓA CHUNG
# ============================================================

def clean_scalar(value: Any) -> str:
    """
    Chuyển một giá trị metadata thành chuỗi sạch.
    """
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
    """
    Chuẩn hóa ID giữa JSONL và metadata.csv.

    Ví dụ:
    132934      -> "132934"
    132934.0    -> "132934"
    " 132934 "  -> "132934"
    """
    document_id = clean_scalar(value)

    if re.fullmatch(r"\d+\.0", document_id):
        document_id = document_id[:-2]

    return document_id


def normalize_status(value: Any) -> str:
    """
    Chuẩn hóa trạng thái để phục vụ so sánh.

    Ví dụ:
    " Còn  hiệu lực " -> "còn hiệu lực"
    """
    status = clean_scalar(value)

    return status.casefold()


def normalize_unicode(text: str) -> str:
    """
    Giải mã HTML entity, chuẩn hóa Unicode và loại ký tự ẩn.
    """
    if not text:
        return ""

    # Chuyển &nbsp;, &amp;, &quot;... về ký tự thật.
    text = html.unescape(text)

    # Chuẩn hóa Unicode tiếng Việt.
    text = unicodedata.normalize("NFC", text)

    # Non-breaking space thành khoảng trắng thông thường.
    text = text.replace("\u00a0", " ")

    # Xóa soft hyphen.
    text = text.replace("\u00ad", "")

    # Xóa BOM và các ký tự zero-width.
    text = re.sub(
        r"[\u200b\u200c\u200d\u2060\ufeff]",
        "",
        text,
    )

    # Chuẩn hóa các loại khoảng trắng Unicode.
    text = re.sub(
        r"[\u1680\u2000-\u200a\u202f\u205f\u3000]",
        " ",
        text,
    )

    return text


def remove_control_characters(text: str) -> str:
    """
    Xóa ký tự điều khiển nhưng vẫn giữ newline và tab.
    """
    result = []

    for character in text:
        if character in {"\n", "\t"}:
            result.append(character)
            continue

        if unicodedata.category(character) != "Cc":
            result.append(character)

    return "".join(result)


# ============================================================
# LÀM SẠCH HTML
# ============================================================

def is_noise_line(line: str) -> bool:
    """
    Kiểm tra một dòng có phải văn bản rác hay không.
    """
    line = line.strip()

    if not line:
        return True

    return any(
        pattern.fullmatch(line)
        for pattern in NOISE_LINE_PATTERNS
    )


def normalize_line(line: str) -> str:
    """
    Chuẩn hóa khoảng trắng và dấu câu trong một dòng.
    """
    line = normalize_unicode(line)
    line = remove_control_characters(line)

    # Nhiều khoảng trắng thành một khoảng trắng.
    line = re.sub(r"[ \t]+", " ", line)

    # Xóa khoảng trắng trước dấu câu.
    line = re.sub(
        r"\s+([,.;:!?%)\]])",
        r"\1",
        line,
    )

    # Xóa khoảng trắng ngay sau dấu mở ngoặc.
    line = re.sub(
        r"([(\[])\s+",
        r"\1",
        line,
    )

    return line.strip()


def html_to_text(content_html: str) -> str:
    """
    Chuyển HTML thành văn bản thuần.

    Giữ cấu trúc đoạn, Điều, Khoản và Điểm để phục vụ chunking.
    """
    if not isinstance(content_html, str):
        return ""

    if not content_html.strip():
        return ""

    soup = BeautifulSoup(
        content_html,
        "html.parser",
    )

    # Loại bỏ thành phần không phải nội dung.
    unwanted_tags = [
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "canvas",
        "iframe",
        "form",
        "button",
    ]

    for tag in soup.find_all(unwanted_tags):
        tag.decompose()

    root = soup.body if soup.body else soup

    # Chuyển thẻ br thành xuống dòng.
    for br_tag in root.find_all("br"):
        br_tag.replace_with("\n")

    # Đánh dấu ranh giới các thẻ dạng khối bằng newline.
    block_tags = [
        "p",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "li",
        "ul",
        "ol",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "table",
        "tr",
        "td",
        "th",
    ]

    for tag in list(root.find_all(block_tags)):
        tag.insert_before("\n")
        tag.insert_after("\n")

    # separator=" " giữ nội dung trong các thẻ inline như strong, em.
    text = root.get_text(separator=" ")

    text = normalize_unicode(text)
    text = remove_control_characters(text)

    cleaned_lines: list[str] = []

    for raw_line in text.splitlines():
        line = normalize_line(raw_line)

        if not line:
            continue

        if is_noise_line(line):
            continue

        # Tránh các dòng bị lặp liên tiếp.
        if cleaned_lines and cleaned_lines[-1] == line:
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


# ============================================================
# XỬ LÝ NGÀY VÀ HIỆU LỰC
# ============================================================

def parse_vietnamese_date(value: Any) -> date | None:
    """
    Đọc ngày từ các dạng:

    31/12/2020
    31-12-2020
    2020-12-31
    Ngày hết hiệu lực 31/12/2020
    """
    text = clean_scalar(value)

    if not text:
        return None

    if text in {"...", "-", "--"}:
        return None

    date_patterns = [
        (
            r"(\d{1,2}/\d{1,2}/\d{4})",
            "%d/%m/%Y",
        ),
        (
            r"(\d{1,2}-\d{1,2}-\d{4})",
            "%d-%m-%Y",
        ),
        (
            r"(\d{4}-\d{1,2}-\d{1,2})",
            "%Y-%m-%d",
        ),
    ]

    for pattern, date_format in date_patterns:
        match = re.search(pattern, text)

        if not match:
            continue

        try:
            return datetime.strptime(
                match.group(1),
                date_format,
            ).date()

        except ValueError:
            continue

    return None


def classify_document(
    status: str,
    expiry_date: date | None,
    current_date: date,
) -> tuple[str, str]:
    """
    Phân loại văn bản:

    active:
        Còn hiệu lực và chưa qua ngày hết hiệu lực.

    partial:
        Hết hiệu lực một phần hoặc ngưng hiệu lực một phần.

    excluded:
        Hết hiệu lực toàn bộ, ngưng hiệu lực,
        chưa có hiệu lực hoặc không còn phù hợp.

    unknown:
        Thiếu hoặc chưa xác định trạng thái.
    """

    # Nếu ngày hết hiệu lực đã đến hoặc đã qua thì loại.
    if expiry_date is not None and expiry_date <= current_date:
        return (
            "excluded",
            f"Ngày hết hiệu lực đã qua: "
            f"{expiry_date.strftime('%d/%m/%Y')}",
        )

    if status in ACTIVE_STATUSES:
        return (
            "active",
            "Còn hiệu lực",
        )

    if status in PARTIAL_STATUSES:
        return (
            "partial",
            "Văn bản chỉ còn hiệu lực một phần",
        )

    if status in EXCLUDED_STATUSES:
        return (
            "excluded",
            status,
        )

    if status == "chưa xác định":
        return (
            "unknown",
            "Trạng thái chưa xác định",
        )

    return (
        "unknown",
        "Thiếu trạng thái hiệu lực",
    )


# ============================================================
# ĐỌC VÀ GHÉP METADATA
# ============================================================

def load_metadata(
    metadata_path: Path,
) -> dict[str, dict[str, Any]]:
    """
    Đọc metadata.csv và tạo dictionary tra cứu theo ID.
    """
    dataframe = pd.read_csv(
        metadata_path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
        low_memory=False,
    )

    required_columns = {
        "id",
        "title",
        "tinh_trang_hieu_luc",
        "ngay_het_hieu_luc",
    }

    missing_columns = (
        required_columns
        - set(dataframe.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            "metadata.csv thiếu các cột bắt buộc: "
            f"{missing_text}"
        )

    metadata_by_id: dict[str, dict[str, Any]] = {}

    for _, row in dataframe.iterrows():
        document_id = normalize_id(
            row.get("id")
        )

        if not document_id:
            continue

        metadata_by_id[document_id] = {
            column: clean_scalar(
                row.get(column, "")
            )
            for column in dataframe.columns
        }

    return metadata_by_id


def build_rag_metadata(
    metadata: dict[str, Any],
) -> dict[str, str]:
    """
    Chọn các trường metadata cần đưa vào vector database.
    """
    fields = [
        "title",
        "so_ky_hieu",
        "ngay_ban_hanh",
        "loai_van_ban",
        "ngay_co_hieu_luc",
        "ngay_het_hieu_luc",
        "nguon_thu_thap",
        "ngay_dang_cong_bao",
        "nganh",
        "linh_vuc",
        "co_quan_ban_hanh",
        "chuc_danh",
        "nguoi_ky",
        "pham_vi",
        "thong_tin_ap_dung",
        "tinh_trang_hieu_luc",
    ]

    result: dict[str, str] = {}

    for field in fields:
        value = clean_scalar(
            metadata.get(field, "")
        )

        if value:
            result[field] = value

    return result


# ============================================================
# GHI JSONL
# ============================================================

def write_jsonl_record(
    output_file,
    record: dict[str, Any],
) -> None:
    """
    Ghi một object thành một dòng JSONL.
    """
    output_file.write(
        json.dumps(
            record,
            ensure_ascii=False,
        )
        + "\n"
    )


# ============================================================
# PIPELINE CHÍNH
# ============================================================

def process_jsonl(
    input_path: Path,
    metadata_path: Path,
    active_output_path: Path,
    partial_output_path: Path,
    unknown_output_path: Path,
    audit_output_path: Path,
    summary_output_path: Path,
    remove_html: bool = True,
) -> None:
    """
    Pipeline:

    1. Đọc JSONL.
    2. Ghép metadata theo ID.
    3. Kiểm tra trạng thái hiệu lực.
    4. Loại văn bản hết hiệu lực.
    5. Làm sạch HTML.
    6. Xuất các nhóm dữ liệu riêng.
    """

    if not input_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file nội dung: "
            f"{input_path.resolve()}"
        )

    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy metadata.csv: "
            f"{metadata_path.resolve()}"
        )

    # Tạo thư mục output nếu chưa tồn tại.
    for output_path in [
        active_output_path,
        partial_output_path,
        unknown_output_path,
        audit_output_path,
        summary_output_path,
    ]:
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    print("Đang đọc metadata.csv...")

    metadata_by_id = load_metadata(
        metadata_path
    )

    print(
        "Đã tải "
        f"{len(metadata_by_id):,} "
        "bản ghi metadata."
    )

    current_date = date.today()

    counters = {
        "total_jsonl": 0,
        "active": 0,
        "partial": 0,
        "excluded": 0,
        "unknown": 0,
        "missing_metadata": 0,
        "invalid_json": 0,
        "empty_content": 0,
        "written_active": 0,
        "written_partial": 0,
        "written_unknown": 0,
    }

    audit_rows: list[dict[str, Any]] = []

    print("Đang xử lý dữ liệu JSONL...")

    with (
        input_path.open(
            "r",
            encoding="utf-8-sig",
        ) as input_file,
        active_output_path.open(
            "w",
            encoding="utf-8",
        ) as active_file,
        partial_output_path.open(
            "w",
            encoding="utf-8",
        ) as partial_file,
        unknown_output_path.open(
            "w",
            encoding="utf-8",
        ) as unknown_file,
    ):
        for line_number, raw_line in enumerate(
            input_file,
            start=1,
        ):
            line = raw_line.strip()

            if not line:
                continue

            counters["total_jsonl"] += 1

            # Hiển thị tiến trình mỗi 10.000 dòng.
            if counters["total_jsonl"] % 10000 == 0:
                print(
                    "Đã xử lý "
                    f"{counters['total_jsonl']:,} "
                    "bản ghi..."
                )

            try:
                record = json.loads(line)

            except json.JSONDecodeError as error:
                counters["invalid_json"] += 1

                audit_rows.append({
                    "line_number": line_number,
                    "id": "",
                    "classification": "invalid_json",
                    "status": "",
                    "expiry_date": "",
                    "content_status": "Không đọc được JSON",
                    "reason": str(error),
                    "title": "",
                })

                continue

            if not isinstance(record, dict):
                counters["invalid_json"] += 1

                audit_rows.append({
                    "line_number": line_number,
                    "id": "",
                    "classification": "invalid_json",
                    "status": "",
                    "expiry_date": "",
                    "content_status": "JSON không phải object",
                    "reason": "Bản ghi không phải dictionary",
                    "title": "",
                })

                continue

            document_id = normalize_id(
                record.get("id")
            )

            content_html = record.get(
                "content_html",
                "",
            )

            # Hỗ trợ thêm trường content hoặc text nếu có.
            if not content_html:
                content_html = record.get(
                    "content",
                    record.get("text", ""),
                )

            metadata = metadata_by_id.get(
                document_id
            )

            # Không tìm thấy metadata.
            if metadata is None:
                counters["missing_metadata"] += 1
                counters["unknown"] += 1

                content_clean = html_to_text(
                    content_html
                )

                content_status = (
                    "Có nội dung"
                    if content_clean
                    else "Nội dung rỗng"
                )

                if not content_clean:
                    counters["empty_content"] += 1

                audit_rows.append({
                    "line_number": line_number,
                    "id": document_id,
                    "classification": "unknown",
                    "status": "",
                    "expiry_date": "",
                    "content_status": content_status,
                    "reason": (
                        "Không tìm thấy ID trong "
                        "metadata.csv"
                    ),
                    "title": "",
                })

                if content_clean:
                    unknown_record = {
                        "id": document_id,
                        "content_clean": content_clean,
                        "metadata": {},
                        "classification": "unknown",
                        "review_reason": (
                            "Không tìm thấy metadata"
                        ),
                    }

                    if not remove_html:
                        unknown_record[
                            "content_html"
                        ] = content_html

                    write_jsonl_record(
                        unknown_file,
                        unknown_record,
                    )

                    counters[
                        "written_unknown"
                    ] += 1

                continue

            status_display = clean_scalar(
                metadata.get(
                    "tinh_trang_hieu_luc",
                    "",
                )
            )

            status_key = normalize_status(
                status_display
            )

            expiry_date = parse_vietnamese_date(
                metadata.get(
                    "ngay_het_hieu_luc",
                    "",
                )
            )

            classification, reason = (
                classify_document(
                    status=status_key,
                    expiry_date=expiry_date,
                    current_date=current_date,
                )
            )

            counters[classification] += 1

            expiry_date_text = (
                expiry_date.isoformat()
                if expiry_date
                else ""
            )

            title = clean_scalar(
                metadata.get("title", "")
            )

            # Văn bản bị loại không cần xử lý HTML.
            if classification == "excluded":
                audit_rows.append({
                    "line_number": line_number,
                    "id": document_id,
                    "classification": classification,
                    "status": status_display,
                    "expiry_date": expiry_date_text,
                    "content_status": "Không xử lý",
                    "reason": reason,
                    "title": title,
                })

                continue

            content_clean = html_to_text(
                content_html
            )

            if not content_clean:
                counters["empty_content"] += 1

                audit_rows.append({
                    "line_number": line_number,
                    "id": document_id,
                    "classification": classification,
                    "status": status_display,
                    "expiry_date": expiry_date_text,
                    "content_status": "Nội dung rỗng",
                    "reason": reason,
                    "title": title,
                })

                continue

            audit_rows.append({
                "line_number": line_number,
                "id": document_id,
                "classification": classification,
                "status": status_display,
                "expiry_date": expiry_date_text,
                "content_status": "Đã làm sạch",
                "reason": reason,
                "title": title,
            })

            output_record: dict[str, Any] = {
                "id": document_id,
                "content_clean": content_clean,
                "metadata": build_rag_metadata(
                    metadata
                ),
                "classification": classification,
            }

            if not remove_html:
                output_record[
                    "content_html"
                ] = content_html

            if classification == "active":
                write_jsonl_record(
                    active_file,
                    output_record,
                )

                counters["written_active"] += 1

            elif classification == "partial":
                output_record["review_reason"] = (
                    "Cần xác định điều, khoản nào "
                    "vẫn còn hiệu lực"
                )

                write_jsonl_record(
                    partial_file,
                    output_record,
                )

                counters["written_partial"] += 1

            else:
                output_record["review_reason"] = (
                    reason
                )

                write_jsonl_record(
                    unknown_file,
                    output_record,
                )

                counters["written_unknown"] += 1

    # ========================================================
    # GHI FILE NHẬT KÝ
    # ========================================================

    audit_fieldnames = [
        "line_number",
        "id",
        "classification",
        "status",
        "expiry_date",
        "content_status",
        "reason",
        "title",
    ]

    with audit_output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as audit_file:
        writer = csv.DictWriter(
            audit_file,
            fieldnames=audit_fieldnames,
        )

        writer.writeheader()
        writer.writerows(audit_rows)

    # Ghi file tổng kết JSON.
    summary = {
        "processing_date": (
            current_date.isoformat()
        ),
        "input_file": str(input_path),
        "metadata_file": str(metadata_path),
        "outputs": {
            "active": str(
                active_output_path
            ),
            "partial": str(
                partial_output_path
            ),
            "unknown": str(
                unknown_output_path
            ),
            "audit": str(
                audit_output_path
            ),
        },
        "statistics": counters,
    }

    with summary_output_path.open(
        "w",
        encoding="utf-8",
    ) as summary_file:
        json.dump(
            summary,
            summary_file,
            ensure_ascii=False,
            indent=2,
        )

    # ========================================================
    # HIỂN THỊ KẾT QUẢ
    # ========================================================

    print()
    print("=" * 60)
    print("KẾT QUẢ LỌC VÀ LÀM SẠCH DỮ LIỆU")
    print("=" * 60)

    print(
        f"Tổng bản ghi JSONL:          "
        f"{counters['total_jsonl']:,}"
    )

    print(
        f"Còn hiệu lực:                "
        f"{counters['active']:,}"
    )

    print(
        f"Hiệu lực một phần:           "
        f"{counters['partial']:,}"
    )

    print(
        f"Đã loại do hết hiệu lực:     "
        f"{counters['excluded']:,}"
    )

    print(
        f"Chưa xác định:               "
        f"{counters['unknown']:,}"
    )

    print(
        f"Thiếu metadata:              "
        f"{counters['missing_metadata']:,}"
    )

    print(
        f"JSON lỗi:                    "
        f"{counters['invalid_json']:,}"
    )

    print(
        f"Nội dung rỗng:               "
        f"{counters['empty_content']:,}"
    )

    print("-" * 60)

    print(
        f"Đã ghi file còn hiệu lực:    "
        f"{counters['written_active']:,}"
    )

    print(
        f"Đã ghi file một phần:        "
        f"{counters['written_partial']:,}"
    )

    print(
        f"Đã ghi file cần kiểm tra:    "
        f"{counters['written_unknown']:,}"
    )

    print("=" * 60)

    print(
        "Dữ liệu dùng cho RAG:\n"
        f"  {active_output_path.resolve()}"
    )

    print(
        "Dữ liệu hiệu lực một phần:\n"
        f"  {partial_output_path.resolve()}"
    )

    print(
        "Dữ liệu cần kiểm tra:\n"
        f"  {unknown_output_path.resolve()}"
    )

    print(
        "Nhật ký lọc:\n"
        f"  {audit_output_path.resolve()}"
    )

    print(
        "File tổng kết:\n"
        f"  {summary_output_path.resolve()}"
    )


# ============================================================
# CHẠY CHƯƠNG TRÌNH
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Làm sạch HTML, chuẩn hóa Unicode, ghép metadata "
            "và lọc văn bản pháp luật hết hiệu lực."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path(
            "data_local/"
            "vietnamese_legal_content.jsonl"
        ),
        help=(
            "Đường dẫn file JSONL chứa nội dung HTML."
        ),
    )

    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path(
            "data_local/metadata.csv"
        ),
        help=(
            "Đường dẫn file metadata.csv."
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data_local"),
        help=(
            "Thư mục lưu các file kết quả."
        ),
    )

    parser.add_argument(
        "--keep-html",
        action="store_true",
        help=(
            "Giữ lại trường content_html trong output."
        ),
    )

    args = parser.parse_args()

    output_directory: Path = (
        args.output_dir
    )

    process_jsonl(
        input_path=args.input,
        metadata_path=args.metadata,
        active_output_path=(
            output_directory
            / "vietnamese_legal_active_clean.jsonl"
        ),
        partial_output_path=(
            output_directory
            / "vietnamese_legal_partial_review.jsonl"
        ),
        unknown_output_path=(
            output_directory
            / "vietnamese_legal_unknown_review.jsonl"
        ),
        audit_output_path=(
            output_directory
            / "legal_filter_audit.csv"
        ),
        summary_output_path=(
            output_directory
            / "legal_filter_summary.json"
        ),
        remove_html=not args.keep_html,
    )


if __name__ == "__main__":
    main()