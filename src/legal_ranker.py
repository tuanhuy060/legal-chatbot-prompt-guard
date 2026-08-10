from datetime import datetime
import math


# =====================================
# 1. THỨ BẬC LOẠI VĂN BẢN
# =====================================

LEGAL_TYPE_SCORE = {

    "Hiến pháp": 1.0,

    "Bộ luật": 0.95,

    "Luật": 0.95,

    "Nghị quyết": 0.85,

    "Nghị định": 0.75,

    "Thông tư": 0.65,

    "Quyết định": 0.45,

    "Chỉ thị": 0.35
}



# =====================================
# 2. PARSE DATE
# =====================================

def parse_date(date_string):

    if not date_string:
        return None

    formats = [
        "%d/%m/%Y",
        "%Y-%m-%d"
    ]

    for fmt in formats:

        try:
            return datetime.strptime(
                date_string,
                fmt
            )

        except:
            pass

    return None



# =====================================
# 3. ĐIỂM ĐỘ MỚI
# =====================================

def calculate_recency(metadata):

    date_value = (
        metadata.get(
            "ngay_co_hieu_luc"
        )
        or
        metadata.get(
            "ngay_ban_hanh"
        )
    )


    document_date = parse_date(
        date_value
    )


    if not document_date:
        return 0.3


    today = datetime.now()


    age_years = (
        today - document_date
    ).days / 365


    # 10 năm giảm còn khoảng 50%
    score = math.exp(
        -0.07 * age_years
    )


    return score



# =====================================
# 4. LOẠI VĂN BẢN
# =====================================

def get_legal_type_score(metadata):

    doc_type = metadata.get(
        "loai_van_ban",
        ""
    )


    for key, value in LEGAL_TYPE_SCORE.items():

        if key.lower() in doc_type.lower():

            return value


    return 0.3



# =====================================
# 5. FINAL LEGAL SCORE
# =====================================

def calculate_legal_score(item):

    metadata = (
        item["document"]
        .metadata
    )


    rerank_score = item.get(
        "reranker_score",
        0
    )


    recency = calculate_recency(
        metadata
    )


    legal_type = get_legal_type_score(
        metadata
    )


    final_score = (

        0.65 * rerank_score

        +

        0.20 * recency

        +

        0.15 * legal_type

    )


    item["recency_score"] = recency

    item["legal_type_score"] = legal_type

    item["legal_final_score"] = final_score


    return item



# =====================================
# APPLY RANKING
# =====================================

def legal_rerank(
        reranked_documents,
        top_k=5
):


    results = []


    for item in reranked_documents:

        results.append(
            calculate_legal_score(
                item
            )
        )


    results.sort(
        key=lambda x:
        x["legal_final_score"],
        reverse=True
    )


    return results[:top_k]