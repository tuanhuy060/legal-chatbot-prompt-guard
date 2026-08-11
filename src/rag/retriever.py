"""
Module truy vấn ứng viên pháp luật tương đồng bằng Vector Search (ChromaDB + BGE-M3).
"""
import os
from pathlib import Path
from typing import Any

# Tự động trỏ cache HuggingFace sang ổ D (nếu có) để tránh đầy ổ C
if "HF_HOME" not in os.environ and Path("D:/").exists():
    os.environ["HF_HOME"] = "D:/hf_cache"

import torch
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings


class LegalRetriever:
    """Truy vấn các đoạn văn bản pháp luật liên quan dựa trên khoảng cách vector."""

    def __init__(
        self,
        db_dir: str = "chroma_legal_db",
        collection_name: str = "legal_documents",
        model_name: str = "BAAI/bge-m3"
    ):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Retriever] Khởi tạo BGE-M3 trên thiết bị: {self.device.upper()}...")

        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": self.device},
            encode_kwargs={
                "normalize_embeddings": True,
                "batch_size": 8 if self.device == "cuda" else 4
            }
        )

        print(f"[Retriever] Đang kết nối ChromaDB tại '{db_dir}'...")
        self.vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=db_dir
        )
        print("[Retriever] Sẵn sàng phục vụ truy vấn.")

    def retrieve(self, query: str, k: int = 30) -> list[dict[str, Any]]:
        """Tìm kiếm top K văn bản tương đồng nhất với câu hỏi."""
        results = self.vector_store.similarity_search_with_score(query, k=k)

        candidates = []
        for doc, distance in results:
            candidates.append({
                "document": doc,
                "vector_distance": float(distance)
            })

        return candidates
