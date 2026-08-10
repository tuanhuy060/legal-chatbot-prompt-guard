# test_retriever.py

from retriever import LegalRetriever


retriever = LegalRetriever()

query = "Luật Doanh nghiệp 2020 "

results = retriever.retrieve(
    query,
    k=20
)


print("\nQUERY:")
print(query)

print("\n" + "=" * 100)


for i, item in enumerate(results, 1):

    doc = item["document"]

    print(f"\nRESULT {i}")

    print(
        "Distance:",
        item["vector_distance"]
    )

    print(
        "Văn bản:",
        doc.metadata.get("title", "")
    )

    print(
        "Số:",
        doc.metadata.get("so_ky_hieu", "")
    )

    print(
        "Ngày hiệu lực:",
        doc.metadata.get("ngay_co_hieu_luc", "")
    )

    print("\nContent:")
    print(doc.page_content[:600])

    print("-" * 100)