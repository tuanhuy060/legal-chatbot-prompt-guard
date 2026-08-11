"""
Module chấm điểm đặc thù văn bản pháp luật: Thứ bậc hiệu lực + Độ mới + Điểm ngữ nghĩa.
"""
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

    # Hàm suy giảm số mũ: e^(-0.07 * age_years)
    score = math.exp(-0.07 * age_years)
    return score


def get_legal_type_score(metadata: dict[str, Any]) -> float:
    """Xác định điểm thứ bậc hiệu lực của loại văn bản."""
    doc_type = str(metadata.get("loai_van_ban", "")).lower()

    for key, value in LEGAL_TYPE_SCORE.items():
        if key.lower() in doc_type:
            return value

    return 0.3  # Mặc định cho các văn bản không xác định rõ loại


def calculate_legal_score(
    item: dict[str, Any],
    weight_rerank: float = 0.65,
    weight_recency: float = 0.20,
    weight_type: float = 0.15,
) -> dict[str, Any]:
    """Tính điểm tổng hợp cuối cùng cho một ứng viên văn bản pháp luật."""
    metadata = getattr(item["document"], "metadata", {}) or {}

    rerank_score = item.get("reranker_score", 0.0)
    recency = calculate_recency(metadata)
    legal_type = get_legal_type_score(metadata)

    final_score = (
        weight_rerank * rerank_score
        + weight_recency * recency
        + weight_type * legal_type
    )

    item["recency_score"] = recency
    item["legal_type_score"] = legal_type
    item["legal_final_score"] = final_score
    return item


def legal_rerank(
    reranked_documents: list[dict[str, Any]],
    top_k: int = 5,
    weight_rerank: float = 0.65,
    weight_recency: float = 0.20,
    weight_type: float = 0.15,
) -> list[dict[str, Any]]:
    """Tái sắp xếp danh sách kết quả theo điểm pháp lý tổng hợp (Legal Final Score)."""
    scored_results = [
        calculate_legal_score(
            item,
            weight_rerank=weight_rerank,
            weight_recency=weight_recency,
            weight_type=weight_type,
        )
        for item in reranked_documents
    ]

    scored_results.sort(key=lambda x: x["legal_final_score"], reverse=True)
    return scored_results[:top_k]
