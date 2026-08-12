import sys
import traceback
sys.stdout.reconfigure(encoding='utf-8')

try:
    from src.rag.retriever import LegalRetriever
    from src.rag.reranker import LegalReranker
    from src.rag.legal_ranker import legal_rerank

    retriever = LegalRetriever()
    print("Collection count:", retriever.vector_store._collection.count())

    query = "Tôi 17 tuổi có được mở công ty TNHH không?"
    candidates = retriever.retrieve(query, k=20)
    print(f"Retrieved {len(candidates)} candidates from ChromaDB:")
    for i, c in enumerate(candidates, 1):
        doc = c["document"]
        meta = doc.metadata or {}
        print(f"  {i}. Title: {meta.get('title')} | So: {meta.get('so_ky_hieu')} | Dist: {c.get('vector_distance'):.4f}")
        body = doc.page_content.split('---')[-1].strip()[:100].replace('\n', ' ')
        print(f"     Preview: {body}")

    reranker = LegalReranker()
    reranked = reranker.rerank(query, candidates, top_k=10)
    print("\nTop reranked:")
    for i, r in enumerate(reranked, 1):
        doc = r["document"]
        meta = doc.metadata or {}
        print(f"  {i}. Rerank score: {r.get('reranker_score'):.4f} | {meta.get('title')} | {meta.get('so_ky_hieu')}")

    final = legal_rerank(reranked, top_k=5)
    print("\nFinal Legal Ranked:")
    for i, f in enumerate(final, 1):
        doc = f["document"]
        meta = doc.metadata or {}
        print(f"  {i}. Final score: {f.get('legal_final_score'):.4f} | Recency: {f.get('recency_score'):.4f} | Type: {f.get('legal_type_score'):.4f} | {meta.get('title')}")
        body = doc.page_content.split('---')[-1].strip()[:150].replace('\n', ' ')
        print(f"     Content: {body}")

except Exception as e:
    traceback.print_exc()

