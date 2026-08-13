# 📡 TÀI LIỆU KỸ THUẬT RESTful API & STREAMING (SSE)
## HỆ THỐNG TRỢ LÝ PHÁP LUẬT THÔNG MINH - LEGALGUARD AI

Hệ thống cung cấp giao diện lập trình ứng dụng (API) hiệu năng cao được xây dựng trên nền tảng **FastAPI (Asynchronous Python Web Framework)**, hỗ trợ giao thức thời gian thực **Server-Sent Events (SSE)** cho tính năng phản hồi văn bản từng token (Token-by-Token Streaming).

* **Base URL:** `http://127.0.0.1:8000`
* **Giao thức:** `HTTP/1.1`, `HTTP/2`
* **Định dạng dữ liệu:** `application/json`, `text/event-stream`
* **Mã hóa ký tự:** `UTF-8`

---

## 📑 BẢNG TỔNG HỢP DANH SÁCH ENDPOINTS

| STT | Phương thức | Endpoint URI | Phân loại | Mô tả chức năng |
|:---|:---|:---|:---|:---|
| 1 | `POST` | `/api/chat/stream` | **Streaming (SSE)** | Luồng tư vấn pháp lý thời gian thực qua 5 tầng xử lý |
| 2 | `POST` | `/api/sessions` | **Session API** | Tạo một phiên hội thoại tư vấn mới |
| 3 | `GET` | `/api/sessions` | **Session API** | Lấy danh sách các phiên hội thoại theo `user_id` |
| 4 | `GET` | `/api/sessions/{session_id}` | **Session API** | Lấy chi tiết nội dung và lịch sử tin nhắn của một phiên |
| 5 | `DELETE` | `/api/sessions/{session_id}` | **Session API** | Xóa vĩnh viễn một phiên trò chuyện khỏi NoSQL DB |
| 6 | `GET` | `/api/security-logs` | **Security Audit** | Lấy nhật ký các vụ tấn công bị Prompt Guard chặn |
| 7 | `GET` | `/api/health` | **System Monitor** | Kiểm tra trạng thái hoạt động và thông số kỹ thuật |

---

## 🛠️ CHI TIẾT CÁC ENDPOINT

### 1. `POST /api/chat/stream` — Luồng Tư Vấn Streaming Thời Gian Thực
* **Mô tả:** Tiếp nhận câu hỏi người dùng, thực thi tuần tự qua **Tầng 1 (Prompt Guard) $\rightarrow$ Tầng 2 (Retriever) $\rightarrow$ Tầng 3 (Reranker) $\rightarrow$ Tầng 4 (Legal Score) $\rightarrow$ Tầng 5 (LLM Generation)** và đẩy dữ liệu về client dưới dạng luồng sự kiện SSE.
* **Content-Type:** `application/json`
* **Response Media-Type:** `text/event-stream; charset=utf-8`

#### Request Body Schema:
```json
{
  "session_id": "8f3b2a1c",
  "user_id": "user_1",
  "query": "Người 17 tuổi có được thành lập công ty TNHH một thành viên không?"
}
```

#### Các sự kiện SSE (Server-Sent Events) trả về:

##### A. Trường hợp An toàn (Tiến hành RAG + Sinh câu trả lời):
```http
HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8
Transfer-Encoding: chunked

data: {"type": "guard_result", "is_safe": true, "risk_score": 0.0, "risk_level": "safe", "matched_patterns": []}

data: {"type": "citations", "citations": [{"title": "Luật Doanh nghiệp số 59/2020/QH14", "so_ky_hieu": "59/2020/QH14", "score": 0.9412, "snippet": "Điều 17. Quyền thành lập, góp vốn... Người chưa thành niên không có quyền thành lập doanh nghiệp..."}]}

data: {"type": "token", "token": "📌 **CĂN CỨ PHÁP LÝ:**\n"}
data: {"type": "token", "token": "- Khoản 2 Điều 17 Luật Doanh nghiệp số 59/2020/QH14..."}
data: {"type": "token", "token": "\n\n🎯 **KẾT LUẬN:** Bạn không được phép thành lập doanh nghiệp khi 17 tuổi."}

data: {"type": "done", "full_response": "..."}
```

##### B. Trường hợp Bị chặn bởi Prompt Guard (Tấn công bảo mật):
```http
HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8

data: {"type": "guard_result", "is_safe": false, "risk_score": 0.95, "risk_level": "attack", "matched_patterns": ["Direct Illegal Act Assistance (VI)"]}

data: {"type": "blocked", "message": "⛔ **TỪ CHỐI PHỤC VỤ (CẢNH BÁO BẢO MẬT)**\n\nYêu cầu của bạn đã bị chặn bởi hệ thống phòng vệ **Prompt Guard** do vi phạm quy tắc an toàn: `Direct Illegal Act Assistance (VI)`.\n\n*Hệ thống từ chối cung cấp hướng dẫn cho các hành vi phạm pháp hoặc lách luật.*"}

data: {"type": "done", "full_response": "⛔ TỪ CHỐI PHỤC VỤ..."}
```

---

### 2. `POST /api/sessions` — Tạo Phiên Hội Thoại Mới
* **Mô tả:** Khởi tạo một phiên trò chuyện độc lập trong cơ sở dữ liệu NoSQL.
* **Request Body:**
```json
{
  "user_id": "user_1",
  "title": "Tư vấn thành lập doanh nghiệp"
}
```
* **Response (HTTP 200 OK):**
```json
{
  "status": "success",
  "session": {
    "session_id": "c8a1e2f4",
    "user_id": "user_1",
    "title": "Tư vấn thành lập doanh nghiệp",
    "created_at": "2026-08-13 10:15:30",
    "updated_at": "2026-08-13 10:15:30",
    "messages": []
  }
}
```

---

### 3. `GET /api/sessions` — Lấy Danh Sách Phiên Của Người Dùng
* **Query Parameters:**
  * `user_id` *(string, optional, mặc định "user_1")*: Định danh người dùng.
* **Response (HTTP 200 OK):**
```json
{
  "status": "success",
  "total": 2,
  "sessions": [
    {
      "session_id": "c8a1e2f4",
      "user_id": "user_1",
      "title": "Người 17 tuổi có được thành lập công ty...",
      "created_at": "2026-08-13 10:15:30",
      "updated_at": "2026-08-13 10:16:02"
    }
  ]
}
```

---

### 4. `GET /api/sessions/{session_id}` — Lấy Chi Tiết Lịch Sử Chat
* **Path Parameters:**
  * `session_id` *(string, bắt buộc)*: Mã định danh phiên.
* **Query Parameters:**
  * `user_id` *(string, optional)*: Dùng để xác thực cô lập dữ liệu người dùng.
* **Response (HTTP 200 OK):**
```json
{
  "status": "success",
  "session": {
    "session_id": "c8a1e2f4",
    "user_id": "user_1",
    "title": "Tư vấn luật lao động",
    "created_at": "2026-08-13 10:15:30",
    "updated_at": "2026-08-13 10:16:02",
    "messages": [
      {
        "id": "m1a2b3c4",
        "role": "user",
        "content": "Thời giờ làm việc bình thường là bao nhiêu tiếng?",
        "timestamp": "2026-08-13 10:15:35",
        "citations": [],
        "guard_meta": {}
      },
      {
        "id": "m5e6f7g8",
        "role": "assistant",
        "content": "📌 CĂN CỨ PHÁP LÝ: Điều 105 Bộ luật Lao động 2019...",
        "timestamp": "2026-08-13 10:15:42",
        "citations": [
          {
            "title": "Bộ luật Lao động số 45/2019/QH14",
            "so_ky_hieu": "45/2019/QH14",
            "score": 0.952
          }
        ],
        "guard_meta": {
          "is_safe": true,
          "risk_score": 0.0
        }
      }
    ]
  }
}
```

---

### 5. `DELETE /api/sessions/{session_id}` — Xóa Phiên Hội Thoại
* **Mô tả:** Xóa toàn bộ lịch sử tin nhắn và dữ liệu của phiên khỏi NoSQL Database.
* **Response (HTTP 200 OK):**
```json
{
  "status": "success",
  "message": "Session c8a1e2f4 đã được xóa thành công."
}
```

---

### 6. `GET /api/security-logs` — Nhật Ký Bảo Mật Prompt Guard
* **Query Parameters:**
  * `limit` *(int, optional, mặc định 50)*: Số lượng log muốn lấy.
* **Response (HTTP 200 OK):**
```json
{
  "status": "success",
  "total": 1,
  "logs": [
    {
      "log_id": "sec_7a8b9c0d",
      "timestamp": "2026-08-13 10:45:12",
      "user_id": "user_1",
      "prompt": "chỉ tôi cách trốn thuế",
      "risk_level": "attack",
      "risk_score": 0.95,
      "matched_rules": ["Direct Illegal Act Assistance (VI)"],
      "action": "BLOCKED"
    }
  ]
}
```

---

### 7. `GET /api/health` — Giám Sát Trạng Thái Hệ Thống
* **Response (HTTP 200 OK):**
```json
{
  "status": "online",
  "vector_chunks": 12480,
  "embedding_model": "BAAI/bge-m3",
  "reranker_model": "BAAI/bge-reranker-v2-m3",
  "llm_model": "Qwen/Qwen2.5-0.5B-Instruct",
  "recent_blocked_attacks": 13
}
```

---

## 💻 VÍ DỤ GỌI API BẰNG CURL & PYTHON

### Python Requests (SSE Stream):
```python
import json
import requests

url = "http://127.0.0.1:8000/api/chat/stream"
payload = {
    "user_id": "user_1",
    "query": "Quy định về thời giờ làm việc của người lao động?"
}

response = requests.post(url, json=payload, stream=True)
for line in response.iter_lines():
    if line:
        decoded_line = line.decode("utf-8")
        if decoded_line.startswith("data: "):
            event = json.loads(decoded_line[6:])
            if event["type"] == "token":
                print(event["token"], end="", flush=True)
```
