import json
import re
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Cấu hình Recursive splitter cho những "Điều" quá dài
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000, 
    chunk_overlap=150,
    separators=["\n\n", "\n", ".", " ", ""]
)

def create_context_header(metadata):
    """
    Tạo đoạn text bối cảnh để gắn vào đầu mỗi chunk.
    """
    title = metadata.get("title", "")
    so_ky_hieu = metadata.get("so_ky_hieu", "")
    co_quan = metadata.get("co_quan_ban_hanh", "")
    ngay = metadata.get("ngay_ban_hanh", "")
    pham_vi = metadata.get("pham_vi", "")
    
    header = (
        f"[BỐI CẢNH VĂN BẢN]\n"
        f"Tên văn bản: {title}\n"
        f"Số ký hiệu: {so_ky_hieu} | Cơ quan ban hành: {co_quan} | Ngày ban hành: {ngay} | Phạm vi áp dụng: {pham_vi}\n"
        f"---\n"
    )
    return header

def chunk_legal_document(doc_json):
    """
    Hàm chunking một văn bản pháp luật (đã tích hợp xử lý gom chunk ngắn)
    """
    content = doc_json.get("content_clean", "")
    metadata = doc_json.get("metadata", {})
    doc_id = doc_json.get("id", "")
    
    context_header = create_context_header(metadata)
    chunks = []
    
    # 1. Tách văn bản theo "Điều X." hoặc "Điều X:"
    parts = re.split(r'\n(Điều \d+[\.\:])', content)
    
    # Phần đầu tiên (trước Điều 1) thường là Quốc hiệu, Tiêu đề và Căn cứ pháp lý
    intro_text = parts[0].strip()
    if intro_text:
        chunk_text = context_header + "[Phần Căn cứ & Lời mở đầu]\n" + intro_text
        chunks.append({
            "doc_id": doc_id,
            "chunk_content": chunk_text,
            "metadata": metadata
        })
    
    # Đặt giới hạn ký tự tối thiểu cho một chunk độc lập
    MIN_LENGTH = 150 
    
    # 2. Ghép các "Điều X." lại với nội dung của nó
    for i in range(1, len(parts), 2):
        dieu_title = parts[i].strip() 
        dieu_content = parts[i+1].strip() if i+1 < len(parts) else ""
        
        full_dieu_text = f"{dieu_title} {dieu_content}"
        
        # --- LOGIC GOM CHUNK NGẮN Ở ĐÂY ---
        # Nếu nội dung Điều khoản này < 150 ký tự và đã có chunk trước đó, 
        # ta nối luôn nội dung này vào chunk liền trước.
        if len(full_dieu_text) < MIN_LENGTH and len(chunks) > 0:
            last_chunk = chunks.pop() # Lấy chunk cuối cùng ra
            last_chunk["chunk_content"] += "\n\n" + full_dieu_text # Nối thêm text
            chunks.append(last_chunk) # Đưa ngược lại vào danh sách
            continue # Bỏ qua phần tạo chunk bên dưới, chạy tiếp vòng lặp
        # -----------------------------------
        
        chunk_text = context_header + full_dieu_text
        
        # 3. Xử lý fallback: Cắt nhỏ tiếp nếu Điều khoản này quá dài (> 1500 ký tự)
        if len(chunk_text) > 1500:
            sub_chunks = text_splitter.split_text(full_dieu_text)
            for j, sub in enumerate(sub_chunks):
                sub_chunk_text = context_header + f"[{dieu_title} - Phần {j+1}]\n" + sub
                chunks.append({
                    "doc_id": doc_id,
                    "chunk_content": sub_chunk_text,
                    "metadata": metadata
                })
        else:
            chunks.append({
                "doc_id": doc_id,
                "chunk_content": chunk_text,
                "metadata": metadata
            })
            
    return chunks


# ==========================================
# THỰC THI CHUNKING VỚI FILE TEST.JSONL
# ==========================================
input_file = "vietnamese_legal_active_clean.jsonl"
output_file = "chunked_TEST.jsonl"
final_rag_chunks = []

print(f"Đang đọc dữ liệu từ file {input_file}...")

try:
    # Đọc file gốc
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                doc_json = json.loads(line)
                doc_chunks = chunk_legal_document(doc_json)
                final_rag_chunks.extend(doc_chunks)

    print(f"Hoàn tất xử lý! Đã tạo ra tổng cộng {len(final_rag_chunks)} chunks.")

    # Ghi ra file mới
    with open(output_file, 'w', encoding='utf-8') as out_f:
        for chunk in final_rag_chunks:
            out_f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
            
    print(f"Đã lưu kết quả thành công tại file: {output_file}")

except FileNotFoundError:
    print(f"Lỗi: Không tìm thấy file '{input_file}'. Vui lòng kiểm tra lại xem file đã nằm cùng thư mục với script Python chưa.")
except Exception as e:
    print(f"Đã xảy ra lỗi không mong muốn: {e}")