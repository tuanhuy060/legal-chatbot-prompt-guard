"""
Module truy vấn ứng viên pháp luật tương đồng bằng Vector Search (ChromaDB + BGE-M3).
Tự động khử trùng lặp nội dung (Deduplication).
"""
import hashlib
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
        db_dir: str = "D:/chroma_legal_db",
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
        """Tìm kiếm top K văn bản tương đồng nhất với câu hỏi và tự động khử trùng lặp."""
        # Lấy gấp đôi ứng viên ban đầu để sau khi khử trùng vẫn đủ k ứng viên độc nhất
        raw_k = min(k * 2, 80)
        results = self.vector_store.similarity_search_with_score(query, k=raw_k)

        candidates = []
        seen_hashes = set()

        for doc, distance in results:
            content_text = doc.page_content.strip()
            if not content_text:
                continue

            # Băm phần thân điều luật để lọc trùng lặp
            body_part = content_text.split("---")[-1].strip() if "---" in content_text else content_text
            content_sig = hashlib.md5(body_part.encode("utf-8")).hexdigest()

            if content_sig in seen_hashes:
                continue
            seen_hashes.add(content_sig)

            candidates.append({
                "document": doc,
                "vector_distance": float(distance)
            })

            if len(candidates) >= k:
                break

        return candidates
