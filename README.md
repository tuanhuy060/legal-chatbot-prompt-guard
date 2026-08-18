Tạo file README cho feature này là đúng lúc. File này nên để bạn gửi cho bạn merge sau, nên tôi viết theo hướng **developer documentation**, không chỉ mô tả ý tưởng.

Tạo file:

```text
README_PERSONAL_DOCUMENT_RAG.md
```

Nội dung:

```md
# PERSONAL DOCUMENT RAG PIPELINE

## Overview

Personal Document RAG is an extension module for the legal chatbot system that allows users to upload their own documents and use those documents as a private knowledge source during conversations.

The pipeline converts uploaded Word documents into searchable vector knowledge while keeping the personal document data separated from the public legal knowledge base.

Current supported input:

- Microsoft Word (.docx)

Example:

```

User uploads:
A5.16.03.docx

System processes:

DOCX
|
v
Markdown
|
v
Semantic Chunking
|
v
Embedding
|
v
ChromaDB
|
v
Personal Retrieval

```

---

# Architecture

```

data/personal_docs

```
A5.16.03.docx

      |
      v
```

personal_loader.py

```
      |
      v
```

A5.16.03.md

```
      |
      v
```

personal_chunker.py

```
      |
      v
```

A5.16.03_chunks.json

```
      |
      v
```

personal_embedding.py

```
      |
      v
```

A5.16.03_embeddings.json

```
      |
      v
```

personal_store.py

```
      |
      v
```

ChromaDB

```
      |
      v
```

personal_retriever.py

```

---

# Components

## 1. Personal Loader

File:

```

src/data/personal_loader.py

```

Purpose:

Convert DOCX documents into Markdown format.

Responsibilities:

- Validate DOCX input
- Extract paragraphs
- Extract tables
- Generate Markdown structure
- Add document metadata

Example output:

```

A5.16.03.docx

```
    |

    v
```

A5.16.03.md

````

Generated metadata:

```md
<!-- DOCUMENT_TYPE: contract -->
<!-- CATEGORY: real_estate -->
<!-- DOMAIN: legal -->
````

---

# 2. Personal Chunker

File:

```
src/data/personal_chunker.py
```

Purpose:

Convert Markdown documents into semantic chunks.

Chunking strategy:

* Heading aware
* Contract clause aware
* Section preserving

The system prioritizes document structure instead of fixed-size splitting.

Example:

Input:

```
## ĐIỀU 6: NGHĨA VỤ VÀ QUYỀN CỦA BÊN B

Trong trường hợp bên B từ chối...
```

Output:

```json
{
    "type": "clause",
    "section": "ĐIỀU 6: NGHĨA VỤ VÀ QUYỀN CỦA BÊN B",
    "content": "..."
}
```

---

# 3. Embedding

File:

```
src/rag/personal_embedding.py
```

Model:

```
BAAI/bge-m3
```

Purpose:

Convert document chunks into vector representations.

Input:

```
A5.16.03_chunks.json
```

Output:

```
A5.16.03_embeddings.json
```

Each chunk contains:

```json
{
    "content": "...",

    "metadata": {},

    "embedding": []
}
```

---

# 4. Vector Storage

File:

```
src/rag/personal_store.py
```

Purpose:

Store personal document vectors in ChromaDB.

Storage is separated from the legal knowledge database.

Example:

```
ChromaDB

|
+-- legal_database

|
+-- personal_A5_16_03
```

Each vector stores:

* Chunk ID
* Text content
* Embedding
* Metadata

---

# 5. Personal Retriever

File:

```
src/rag/personal_retriever.py
```

Purpose:

Search user-uploaded documents.

Example query:

```
Nếu bên B không thực hiện chuyển nhượng thì xử lý thế nào?
```

Retrieved result:

```
ĐIỀU 6:
NGHĨA VỤ VÀ QUYỀN CỦA BÊN B
```

The retriever returns:

* Relevant text
* Section information
* Document metadata

---

# Data Flow

## Upload Document

```
User

 |
 v

DOCX File

 |
 v

Personal Loader

 |
 v

Markdown
```

---

## Index Document

```
Markdown

 |
 v

Chunker

 |
 v

Embedding

 |
 v

ChromaDB
```

---

## Query

```
User Question

 |
 v

Query Embedding

 |
 v

Chroma Similarity Search

 |
 v

Relevant Document Chunks
```

---

# Example Test

Question:

```
Nếu bên B không thực hiện chuyển nhượng thì xử lý thế nào?
```

Expected retrieval:

```
Section:

ĐIỀU 6:
NGHĨA VỤ VÀ QUYỀN CỦA BÊN B


Content:

Trong trường hợp bên B từ chối hoặc không thực hiện việc giao kết Văn bản chuyển nhượng...

Bên B có nghĩa vụ trả lại tiền đặt cọc và một khoản tiền phạt cọc...
```

---

# Current Limitations

## Supported format

Currently:

```
.docx
```

Future:

* PDF
* Image OCR
* Excel
* Email attachments

## Metadata cleanup

Some metadata fields may require normalization before production:

Example:

```
contract -->
```

should become:

```
contract
```

## Retrieval Enhancement

Current:

```
Embedding Retrieval
        |
        v
ChromaDB
```

Future:

```
Embedding Retrieval

        |

Cross Encoder Reranker

        |

Final Context
```

---

# Future Integration

Current chatbot:

```
User Query

 |
 v

Legal Retriever

 |
 v

Generator
```

Future:

```
User Query

        |
        v

Prompt Guard

        |
        +----------------+
        |                |
        v                v

Personal Retriever   Legal Retriever

        |                |

        +-------+--------+

                |

                v

          Context Builder

                |

                v

             Generator
```

This allows the assistant to answer using:

1. User private documents
2. Public legal knowledge base

while keeping data sources separated.

````

File này có thể đặt ngay ở root repo:

```text
legal-chatbot-prompt-guard/

├── README.md
├── README_PERSONAL_DOCUMENT_RAG.md
├── src/
├── data/
````

