"""
Module chấm điểm đặc thù văn bản pháp luật: Thứ bậc hiệu lực + Độ mới + Điểm ngữ nghĩa.
Tích hợp bộ lọc Khử trùng lặp (Deduplication) chống trả về các đoạn luật trùng nhau.
"""
import hashlib
import math
from datetime import datetime
from typing import Any

# ============================================================
# 1. THỨ BẬC HIỆU LỰC LOẠI VĂN BẢN (Legal Hierarchy)
# ============================================================
LEGAL_TYPE_SCORE = {
    "Hiến pháp": 1.0,
    "Bộ luật": 0.95,
    "Luật": 0.95,
    "Nghị quyết": 0.85,
    "Nghị định": 0.75,
    "Thông tư": 0.65,
    "Quyết định": 0.45,
    "Chỉ thị": 0.35,
}


def parse_date(date_string: str | None) -> datetime | None:
    """Chuyển đổi chuỗi ngày tháng sang đối tượng datetime."""
    if not date_string:
        return None

    formats = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_string.strip(), fmt)
        except ValueError:
            continue
    return None


def calculate_recency(metadata: dict[str, Any]) -> float:
    """Tính điểm độ mới của văn bản dựa trên hàm suy giảm hàm mũ (10 năm giảm ~50%)."""
    date_value = metadata.get("ngay_co_hieu_luc") or metadata.get("ngay_ban_hanh")
    document_date = parse_date(date_value)

    if not document_date:
        return 0.3

    today = datetime.now()
    age_years = max(0, (today - document_date).days / 365.25)
    score = math.exp(-0.07 * age_years)
    return score


def get_legal_type_score(metadata: dict[str, Any]) -> float:
    """Xác định điểm thứ bậc hiệu lực của loại văn bản theo Luật Ban hành VBQPPL."""
    doc_type = str(metadata.get("loai_van_ban", "")).lower()
    issuer = str(metadata.get("co_quan_ban_hanh", "")).lower()

    # Văn bản địa phương (HĐND, UBND) có thứ bậc hiệu lực thấp nhất
    if "hội đồng nhân dân" in issuer or "hđnd" in issuer or "ủy ban nhân dân" in issuer or "ubnd" in issuer:
        return 0.20

    # Thứ bậc văn bản Trung ương
    if "hiến pháp" in doc_type:
        return 1.0
    elif "bộ luật" in doc_type or "luật" in doc_type:
        return 1.0
    elif "nghị quyết" in doc_type and ("quốc hội" in issuer or "ủy ban thường vụ" in issuer):
        return 0.85
    elif "nghị định" in doc_type:
        return 0.60
    elif "thông tư" in doc_type:
        return 0.50
    elif "quyết định" in doc_type:
        return 0.40
    elif "chỉ thị" in doc_type:
        return 0.30

    return 0.30


def calculate_legal_score(
    item: dict[str, Any],
    weight_rerank: float = 0.80,
    weight_type: float = 0.15,
    weight_recency: float = 0.05,
) -> dict[str, Any]:
    """Tính điểm tổng hợp cuối cùng cho một ứng viên văn bản pháp luật."""
    metadata = getattr(item["document"], "metadata", {}) or {}

    rerank_score = item.get("reranker_score", 0.0)
    recency = calculate_recency(metadata)
    legal_type = get_legal_type_score(metadata)

    final_score = (
        weight_rerank * rerank_score
        + weight_type * legal_type
        + weight_recency * recency
    )

    item["recency_score"] = recency
    item["legal_type_score"] = legal_type
    item["legal_final_score"] = final_score
    return item


def deduplicate_legal_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Loại bỏ các chunk trùng lặp 100% nội dung."""
    unique_items = []
    seen_hashes = set()

    for item in items:
        doc = item["document"]
        content_text = doc.page_content.strip()
        if not content_text:
            continue

        # Lấy phần thân điều luật để băm so sánh
        body_part = content_text.split("---")[-1].strip() if "---" in content_text else content_text
        # Chuẩn hóa khoảng trắng
        normalized = " ".join(body_part.split())[:300]
        content_sig = hashlib.md5(normalized.encode("utf-8")).hexdigest()

        if content_sig in seen_hashes:
            continue
        seen_hashes.add(content_sig)
        unique_items.append(item)

    return unique_items


def diversify_by_source(
    items: list[dict[str, Any]],
    top_k: int = 5,
    max_per_law: int = 1,
) -> list[dict[str, Any]]:
    """Đảm bảo đa dạng nguồn: mỗi bộ luật chỉ xuất hiện tối đa max_per_law chunk.
    Nếu không đủ đa dạng, nới lỏng dần để đủ top_k."""
    # Pass 1: strict diversity (max_per_law per source)
    source_count: dict[str, int] = {}
    diverse = []
    overflow = []

    for item in items:
        meta = getattr(item["document"], "metadata", {}) or {}
        source_id = meta.get("doc_id") or meta.get("so_ky_hieu") or "unknown"
        count = source_count.get(source_id, 0)
        if count < max_per_law:
            source_count[source_id] = count + 1
            diverse.append(item)
        else:
            overflow.append(item)

    # Pass 2: nếu chưa đủ top_k, bổ sung từ overflow
    if len(diverse) < top_k:
        diverse.extend(overflow[: top_k - len(diverse)])

    return diverse[:top_k]


def legal_rerank(
    reranked_documents: list[dict[str, Any]],
    top_k: int = 5,
    weight_rerank: float = 0.80,
    weight_type: float = 0.15,
    weight_recency: float = 0.05,
) -> list[dict[str, Any]]:
    """Tái sắp xếp danh sách kết quả theo điểm pháp lý tổng hợp kèm khử trùng lặp."""
    # 1. Khử trùng lặp trước
    deduped = deduplicate_legal_items(reranked_documents)

    # 2. Tính điểm
    scored_results = [
        calculate_legal_score(
            item,
            weight_rerank=weight_rerank,
            weight_type=weight_type,
            weight_recency=weight_recency,
        )
        for item in deduped
    ]

    # 3. Sắp xếp điểm giảm dần
    scored_results.sort(key=lambda x: x["legal_final_score"], reverse=True)

    # 4. Đa dạng hóa nguồn: ưu tiên lấy từ nhiều bộ luật khác nhau
    diverse_results = diversify_by_source(scored_results, top_k=top_k, max_per_law=1)
    return diverse_results
