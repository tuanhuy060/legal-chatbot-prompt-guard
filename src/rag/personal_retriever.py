from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer


class PersonalRetriever:


    def __init__(
        self,
        persist_dir="data/chroma_personal",
        collection_name="personal_A5_16_03"
    ):

        self.client = chromadb.PersistentClient(
            path=persist_dir
        )


        self.collection = (
            self.client.get_collection(
                collection_name
            )
        )


        self.model = SentenceTransformer(
            "BAAI/bge-m3"
        )



    def search(
        self,
        query,
        top_k=3
    ):


        query_embedding = (
            self.model.encode(
                query,
                normalize_embeddings=True
            )
            .tolist()
        )


        result = (
            self.collection.query(

                query_embeddings=[
                    query_embedding
                ],

                n_results=top_k

            )
        )


        return result




if __name__ == "__main__":


    retriever = PersonalRetriever()



    question = (
        "Nếu bên B không thực hiện "
        "chuyển nhượng thì xử lý thế nào?"
    )


    results = retriever.search(
        question,
        top_k=3
    )


    for i, doc in enumerate(
        results["documents"][0]
    ):

        print("\n==========")
        print(
            "RESULT",
            i + 1
        )

        print(doc[:1000])


        print(
            "\nMETADATA:"
        )

        print(
            results["metadatas"][0][i]
        )