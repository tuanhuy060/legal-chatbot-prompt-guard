# retriever.py

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
import torch


DB_DIR = "./chroma_legal_db"
COLLECTION_NAME = "legal_documents"

device = "cuda" if torch.cuda.is_available() else "cpu"
class LegalRetriever:

    def __init__(self):

        print("Loading BGE-M3 embedding model...")

        self.embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-m3",
            model_kwargs={
                "device": device
            },
            encode_kwargs={
                "normalize_embeddings": True,
                "batch_size": 8
            }
        )

        print("Loading ChromaDB...")

        self.vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=DB_DIR
        )

        print("Retriever ready.")

    def retrieve(self, query, k=30):

        results = self.vector_store.similarity_search_with_score(
            query,
            k=k
        )

        candidates = []

        for doc, distance in results:

            candidates.append({
                "document": doc,
                "vector_distance": float(distance)
            })

        return candidates