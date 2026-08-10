import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import json
import time
import torch
import gc
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

# ==========================================
# CẤU HÌNH ĐƯỜNG DẪN VÀ THÔNG SỐ
# ==========================================
INPUT_FILE = "chunked.jsonl"
DB_DIR = "./chroma_legal_db"
BATCH_SIZE = 5000  # Số lượng chunk lưu vào DB mỗi lượt

# ==========================================
# BƯỚC 1: KHỞI TẠO MÔ HÌNH VÀ VECTOR DB
# ==========================================
print("Đang khởi tạo mô hình BAAI/bge-m3...")
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3",
    model_kwargs={'device': 'cuda'}, 
    encode_kwargs={
        'normalize_embeddings': True,
        'batch_size': 8  # Giữ nguyên cấu hình để tránh tràn RAM
    }
)

print("Đang kết nối ChromaDB...")
vector_store = Chroma(
    collection_name="legal_documents",
    embedding_function=embeddings,
    persist_directory=DB_DIR
)

# ==========================================
# BƯỚC 1.5: TÍNH NĂNG TỰ ĐỘNG CHẠY TIẾP (AUTO-RESUME)
# ==========================================
# Đếm số lượng chunk đã được lưu an toàn trong Database
existing_count = vector_store._collection.count()
print(f"-> Đã tìm thấy {existing_count} chunks trong Database.")

if existing_count > 0:
    print(f"-> Sẽ bỏ qua {existing_count} dòng đầu tiên trong file dữ liệu và chạy tiếp...\n")

# ==========================================
# BƯỚC 2: XỬ LÝ THEO LÔ (BATCH PROCESSING)
# ==========================================
start_time = time.time()
documents_batch = []
total_processed = existing_count # Bắt đầu đếm tiếp từ con số hiện tại

print("Bắt đầu nhúng (embedding) và lưu trữ phần còn lại...")

with open(INPUT_FILE, 'r', encoding='utf-8') as f:
    for line_number, line in enumerate(f):
        # BỎ QUA CÁC DÒNG ĐÃ XỬ LÝ
        if line_number < existing_count:
            continue
            
        if line.strip():
            item = json.loads(line)
            doc = Document(
                page_content=item["chunk_content"],
                metadata=item["metadata"]
            )
            documents_batch.append(doc)
            
            # Khi gom đủ 1 lô, tiến hành lưu vào DB
            if len(documents_batch) >= BATCH_SIZE:
                vector_store.add_documents(documents_batch)
                total_processed += len(documents_batch)
                
                elapsed_time = time.time() - start_time
                chunks_per_sec = len(documents_batch) / elapsed_time
                print(f"Đã xử lý tổng cộng: {total_processed} chunks | Tốc độ lô vừa rồi: {chunks_per_sec:.2f} chunks/s | Đang tiếp tục...")
                
                # Reset lại thời gian cho lô tiếp theo để tính tốc độ chuẩn xác hơn
                start_time = time.time()
                
                # Xóa danh sách và dọn rác
                documents_batch.clear()
                gc.collect()
                torch.cuda.empty_cache()

# Xử lý nốt những chunk còn sót lại cuối cùng
if documents_batch:
    vector_store.add_documents(documents_batch)
    total_processed += len(documents_batch)
    gc.collect()
    torch.cuda.empty_cache()

print("\n==========================================")
print(f"HOÀN TẤT TOÀN BỘ! Đã lưu tổng cộng {total_processed} chunks vào cơ sở dữ liệu.")
print("==========================================")