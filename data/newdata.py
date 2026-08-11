from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="th1nhng0/vietnamese-legal-documents",
    repo_type="dataset",
    local_dir="./vietnamese_legal_docs"
)
