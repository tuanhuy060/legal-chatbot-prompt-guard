# 🛡️ Vietnamese Legal Chatbot with Prompt Guard & Advanced Multi-Stage RAG

Hệ thống tra cứu và tư vấn văn bản Quy phạm Pháp luật Việt Nam ứng dụng kiến trúc **RAG đa tầng (Multi-Stage Retrieval & Specialized Legal Ranking)** kết hợp tầng phòng thủ an ninh **Prompt Guard** ngăn chặn tấn công Prompt Injection / Jailbreak và động cơ suy luận **Legal Chain-of-Thought (Qwen 2.5 1.5B)**.

---

## 🏛️ 1. Kiến trúc hệ thống (System Architecture)

```text
                           [ USER QUERY ]
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │ 1. TẦNG PROMPT GUARD  │ ──► [Phát hiện Injection / Attack] ──► CHẶN & GHI LOG
                     └───────────────────────┘
                                 │ (Safe)
                                 ▼
                     ┌───────────────────────┐
                     │ 2. DENSE VECTOR SEARCH│ ──► Embedding (BAAI/bge-m3)
                     │    (ChromaDB Top 30)  │ ──► MD5 Content Deduplication
                     └───────────────────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │ 3. SEMANTIC RERANKER  │ ──► Cross-Encoder (BAAI/bge-reranker-v2-m3)
                     │       (Top 20)        │ ──► Chuẩn hóa xác suất Sigmoid
                     └───────────────────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │ 4. LEGAL SCORE RANKER │ ──► 80% Điểm ngữ nghĩa (Reranker Score)
                     │     (Top 2 - 5)       │ ──► 15% Thứ bậc hiệu lực (Luật > Nghị định > Thông tư)
                     └───────────────────────┘ ──► 5% Độ mới văn bản (Exponential Recency Decay)
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │ 5. GENERATOR & PII    │ ──► Out-of-Domain Detection (< 0.50 -> Từ chối an toàn)
                     │    (Streaming SSE)    │ ──► Legal CoT Reasoning (Qwen 2.5 1.5B)
                     └───────────────────────┘ ──► Output Sanitizer (Che mờ CCCD, SĐT, STK)
                                 │
                                 ▼
                     [ CÂU TRẢ LỜI CHUẨN XÁC KÈM CĂN CỨ PHÁP LÝ ]
```

---

## 📂 2. Cấu trúc thư mục dự án (Project Structure)

```text
legal-chatbot-prompt-guard/
│
├── data/
│   ├── raw/                 # Dữ liệu gốc (vietnamese_legal_content.jsonl, metadata.csv)
│   └── processed/           # Dữ liệu sau xử lý (vietnamese_legal_active_clean.jsonl, chunked.jsonl)
│
├── chroma_legal_db/         # Cơ sở dữ liệu Vector ChromaDB (HNSW Index)
│
├── src/
│   ├── data/                # TẦNG 1: Xử lý và tiền xử lý dữ liệu
│   │   ├── cleaner.py       # Bóc tách HTML, chuẩn hóa Unicode NFC, lọc văn bản còn hiệu lực
│   │   ├── chunker.py       # Context-Preserving Chunker: Phân đoạn Điều/Khoản & Header injection
│   │   └── session_store.py # Quản lý phiên hội thoại đa lượt và ghi Security Logs (TinyDB NoSQL)
│   │
│   ├── guard/               # TẦNG 2: Kiểm soát an ninh đầu vào
│   │   └── prompt_guard.py  # Ma trận 8 nhóm tấn công Prompt Injection, System Prompt Leak, Jailbreak
│   │
│   └── rag/                 # TẦNG 3 & 4: Multi-Stage RAG & Legal Reasoning
│       ├── indexer.py       # Nhúng vector (BGE-M3 1024 dims) vào ChromaDB (hỗ trợ Auto-resume)
│       ├── retriever.py     # Tìm kiếm Top 30 vector tương đồng + Khử trùng lặp MD5
│       ├── reranker.py      # Cross-Encoder Reranker chấm điểm tương tác ngữ nghĩa sâu
│       ├── legal_ranker.py  # Thuật toán xếp hạng pháp lý 3 tiêu chí + Đa dạng hóa nguồn luật
│       └── generator.py     # Não LLM Qwen 2.5 1.5B (Legal CoT, OOD Refusal, PII Sanitizer)
│
├── static/                  # Giao diện Web Client (HTML5, Vanilla CSS, JS ChatGPT-style)
│   ├── index.html
│   ├── style.css
│   └── app.js
│
├── tests/                   # Kịch bản kiểm thử toàn diện
│   ├── test_guard.py        # Kiểm thử 10 kịch bản an ninh Prompt Guard
│   ├── test_retriever.py    # Kiểm thử riêng tầng Vector Search
│   ├── test_pipeline.py     # Kiểm thử toàn bộ luồng RAG kết nối
│   └── test_legal_eval.py   # Khung đánh giá năng lực pháp lý (8 chỉ số Gated Hierarchical Eval)
│
├── app.py                   # FastAPI Web Server hỗ trợ Server-Sent Events (SSE) Streaming
├── Dockerfile               # Cấu hình containerization
├── requirements.txt         # Danh sách thư viện phụ thuộc
└── README.md                # Tài liệu hướng dẫn sử dụng
```

---

## ⚙️ 3. Cài đặt môi trường (Installation)

### Yêu cầu hệ thống:
- **Python:** 3.10 hoặc 3.11 (64-bit).
- **RAM:** Tối thiểu 8GB (Khuyến nghị 16GB).
- **GPU (Tùy chọn):** NVIDIA GPU với VRAM $\ge$ 6GB (CUDA 11.8 / 12.x) để tăng tốc độ suy luận.

### Bước 1: Tạo và kích hoạt môi trường ảo (PowerShell)
```powershell
# 1. Tạo virtual environment
python -m venv .venv

# 2. Kích hoạt môi trường ảo
.\.venv\Scripts\Activate.ps1
```

### Bước 2: Cài đặt thư viện phụ thuộc
* Nếu máy có **GPU NVIDIA (CUDA 11.8)**:
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt
```
* Nếu máy chạy **CPU thuần túy**:
```powershell
pip install -r requirements.txt
```

---

## 🚀 4. LỆNH CHẠY HỆ THỐNG (QUICK RUN COMMANDS)

### 🌟 1. KHỞI CHẠY GIAO DIỆN WEB CHATBOT (CHÍNH THỨC):
Chạy trực tiếp file `app.py` để khởi động máy chủ Web FastAPI:
```powershell
python app.py
```
*Hoặc sử dụng `uvicorn`:*
```powershell
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```
👉 **Truy cập ứng dụng:** Mở trình duyệt web tại địa chỉ: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

### 🧪 2. CÁC LỆNH CHẠY KIỂM THỬ (TESTING COMMANDS):

#### A. Kiểm thử Tầng Bảo Mật Prompt Guard (10 kịch bản tấn công & an toàn):
```powershell
python -m tests.test_guard
```

#### B. Kiểm thử Riêng Tầng Vector Search (ChromaDB + BGE-M3):
```powershell
python -m tests.test_retriever --query "Luật Doanh nghiệp 2020" --top-k 10
```

#### C. Kiểm thử Toàn bộ Luồng Pipeline (Guard -> Retrieve -> Rerank -> Legal Score):
```powershell
python -m tests.test_pipeline --query "Người dưới 18 tuổi có được thành lập doanh nghiệp không?"
```

#### D. Chạy Bộ Đánh Giá Năng Lực Pháp Lý Chuyên Sâu (8 Chỉ số + Gating Rules):
```powershell
python -m tests.test_legal_eval
```

---

## 🛠️ 5. Xây dựng Data Pipeline từ Dữ liệu Thô (Tùy chọn khi nạp dữ liệu mới)

### Bước 1: Làm sạch dữ liệu và lọc hiệu lực văn bản
```powershell
python -m src.data.cleaner --input data/raw/vietnamese_legal_content.jsonl --metadata data/raw/metadata.csv --output-dir data/processed
```

### Bước 2: Phân đoạn bảo toàn ngữ cảnh Điều/Khoản
```powershell
python -m src.data.chunker --input data/processed/vietnamese_legal_active_clean.jsonl --output data/processed/chunked.jsonl
```

### Bước 3: Tạo Embedding BGE-M3 và nạp vào ChromaDB
```powershell
python -m src.rag.indexer --input data/processed/chunked.jsonl --db-dir chroma_legal_db --batch-size 5000
```
> **Tính năng Auto-Resume:** Script tự động phát hiện số lượng vector đã nạp để tiếp tục chạy nếu bị gián đoạn.

---

## 📊 6. Thuật toán Xếp hạng Pháp lý 3 tiêu chí (Legal Score)

Hệ thống áp dụng công thức chấm điểm đa tiêu chí chuẩn mực:

$$\text{Score}_{\text{Final}} = 0.80 \times \text{Score}_{\text{Reranker}} + 0.15 \times \text{Score}_{\text{Hierarchy}} + 0.05 \times \text{Score}_{\text{Recency}}$$

1. **Điểm Ngữ nghĩa ($\text{Score}_{\text{Reranker}}$ - 80%)**: Chuẩn hóa xác suất Sigmoid từ mô hình Cross-Encoder `BAAI/bge-reranker-v2-m3`:
   $$\text{Score}_{\text{Reranker}} = \frac{1}{1 + e^{-\text{Logits}}}$$
2. **Điểm Thứ bậc hiệu lực ($\text{Score}_{\text{Hierarchy}}$ - 15%)**: Quy định theo Luật Ban hành VBQPPL:
   - Hiến pháp: `1.0`
   - Bộ luật / Luật (Quốc hội): `0.95 - 1.0`
   - Nghị quyết Quốc hội: `0.85`
   - Nghị định Chính phủ: `0.60 - 0.75`
   - Thông tư Bộ ngành: `0.50 - 0.65`
   - Quyết định / Chỉ thị: `0.30 - 0.45`
   - Văn bản địa phương (HĐND, UBND): `0.20`
3. **Điểm Độ mới ($\text{Score}_{\text{Recency}}$ - 5%)**: Hàm suy giảm số mũ theo tuổi văn bản:
   $$\text{Score}_{\text{Recency}} = e^{-0.07 \times \text{Age\_Years}}$$
   *(Văn bản sau 10 năm điểm độ mới giảm còn ~50%, ưu tiên luật mới).*

---

## 🛡️ 7. Tầng Phòng thủ An ninh Prompt Guard

Module `src/guard/prompt_guard.py` đối soát ma trận 8 nhóm tấn công tinh vi:
- **Instruction Override**: Bỏ qua quy tắc cũ, ép làm theo lệnh mới.
- **System Prompt Leak**: Yêu cầu in ra chỉ thị hệ thống và logic nội bộ.
- **Jailbreak Modes**: Chế độ DAN, Developer mode, God mode.
- **Hypothetical Roleplay Hijack**: Đóng vai thẩm phán phá luật, hacker.
- **Academic / Fiction Shield**: Núp bóng nghiên cứu/tiểu thuyết để hỏi cách trốn thuế, rửa tiền, làm giả giấy tờ.
- **Legal Gaslighting**: Thao túng tâm lý rằng luật pháp đã bị bãi bỏ theo sắc lệnh khẩn cấp.
- **Forced Output Prefix**: Ép bot bắt đầu bằng câu xác nhận vi phạm.
- **Data Exfiltration & SQLi/XSS**: Dò hỏi dữ liệu riêng tư phiên khác, chèn mã độc.

**Ngưỡng quyết định rủi ro:**
- `Score >= 0.80`: **ATTACK** $\rightarrow$ Chặn ngay lập tức trong < 5ms & Ghi log an ninh.
- `0.50 <= Score < 0.80`: **SUSPICIOUS** $\rightarrow$ Cho phép xử lý nhưng gắn cờ giám sát.
- `Score < 0.50`: **SAFE** $\rightarrow$ Chuyển tiếp an toàn sang Tầng RAG.

---

## 🐳 8. Chạy với Docker

```powershell
# 1. Build Docker Image
docker build -t legal-chatbot-guard .

# 2. Khởi chạy Container
docker run -d -p 8000:8000 --name legal_chatbot legal-chatbot-guard
```
Truy cập: `http://localhost:8000`
