# reranker.py

from FlagEmbedding import FlagReranker


class LegalReranker:

    def __init__(self):

        print("Loading BGE reranker...")

        self.reranker = FlagReranker(
            "BAAI/bge-reranker-v2-m3",

            query_max_length=256,
            passage_max_length=512,

            use_fp16=True,

            devices=["cuda:0"]
        )

        print("Reranker ready.")

    def rerank(
        self,
        query,
        candidates,
        top_k=5
    ):

        if not candidates:
            return []

        # ---------------------------------------
        # Tạo các cặp:
        #
        # [
        #   [query, document1],
        #   [query, document2],
        #   ...
        # ]
        # ---------------------------------------

        pairs = []

        for item in candidates:

            doc = item["document"]

            pairs.append([
                query,
                doc.page_content
            ])

        # ---------------------------------------
        # RERANK
        # ---------------------------------------

        scores = self.reranker.compute_score(
            pairs,
            normalize=True
        )

        # Nếu chỉ có 1 document,
        # một số version có thể trả scalar

        if not isinstance(scores, list):
            scores = [scores]

        # ---------------------------------------
        # Gắn reranker score vào candidate
        # ---------------------------------------

        reranked_results = []

        for item, score in zip(
            candidates,
            scores
        ):

            reranked_results.append({

                "document":
                    item["document"],

                "vector_distance":
                    item["vector_distance"],

                "reranker_score":
                    float(score)
            })

        # ---------------------------------------
        # Score cao nhất lên đầu
        # ---------------------------------------

        reranked_results.sort(
            key=lambda x:
                x["reranker_score"],
            reverse=True
        )

        return reranked_results[:top_k]