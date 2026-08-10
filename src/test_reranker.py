# test_reranker.py

from retriever import LegalRetriever
from reranker import LegalReranker


# ==========================================
# LOAD MODEL
# ==========================================

retriever = LegalRetriever()

reranker = LegalReranker()


# ==========================================
# QUESTION
# ==========================================

query = (
    "Người dưới 18 tuổi có được "
    "thành lập doanh nghiệp không?"
)


# ==========================================
# RETRIEVE 20 CANDIDATES
# ==========================================

candidates = retriever.retrieve(
    query,
    k=20
)


print("\n")
print("=" * 100)
print("TRƯỚC RERANK")
print("=" * 100)


for i, item in enumerate(candidates[:5], 1):

    doc = item["document"]

    print(f"\n{i}.")

    print(
        doc.metadata.get(
            "title",
            ""
        )
    )

    print(
        "Ngày hiệu lực:",
        doc.metadata.get(
            "ngay_co_hieu_luc",
            ""
        )
    )

    print(
        "Vector distance:",
        item["vector_distance"]
    )


# ==========================================
# RERANK
# ==========================================

from legal_ranker import legal_rerank


# lấy nhiều hơn
# không lấy 5 ngay

reranked = reranker.rerank(
    query,
    candidates,
    top_k=20
)


# thêm legal ranking

results = legal_rerank(
    reranked,
    top_k=5
)


for i, item in enumerate(results, 1):

    doc = item["document"]

    metadata = doc.metadata


    print(f"\nRESULT {i}")

    print(
        "Reranker score:",
        round(
            item.get(
                "reranker_score",
                0
            ),
            4
        )
    )


    print(
        "Recency score:",
        round(
            item.get(
                "recency_score",
                0
            ),
            4
        )
    )


    print(
        "Legal type score:",
        round(
            item.get(
                "legal_type_score",
                0
            ),
            4
        )
    )


    print(
        "FINAL score:",
        round(
            item.get(
                "legal_final_score",
                0
            ),
            4
        )
    )


    print(
        "\nTên:",
        metadata.get(
            "title",
            ""
        )
    )


    print(
        "Loại:",
        metadata.get(
            "loai_van_ban",
            ""
        )
    )


    print(
        "Ngày hiệu lực:",
        metadata.get(
            "ngay_co_hieu_luc",
            ""
        )
    )


    print("\nContent:")
    print(
        doc.page_content[:800]
    )


    print(
        "\n" + "-" * 100
    )