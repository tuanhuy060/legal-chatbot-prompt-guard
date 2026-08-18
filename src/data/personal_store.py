import json
from pathlib import Path
import chromadb
from chromadb.config import Settings


class PersonalStore:


    def __init__(
        self,
        persist_dir="data/chroma_personal"
    ):

        self.client = chromadb.PersistentClient(
            path=persist_dir
        )


    # =========================
    # Load embedding file
    # =========================

    def load_embeddings(
        self,
        file_path
    ):

        path = Path(file_path)


        if not path.exists():

            raise FileNotFoundError(
                file_path
            )


        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)



    # =========================
    # Create collection
    # =========================

    def get_collection(
        self,
        collection_name
    ):

        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={
                "type":
                    "personal_document"
            }
        )



    # =========================
    # Insert vectors
    # =========================

    def insert_chunks(
        self,
        collection_name,
        chunks
    ):


        collection = self.get_collection(
            collection_name
        )


        ids = []

        documents = []

        embeddings = []

        metadatas = []



        for chunk in chunks:


            ids.append(
                chunk["chunk_id"]
            )


            documents.append(
                chunk["content"]
            )


            embeddings.append(
                chunk["embedding"]
            )


            metadata = chunk["metadata"].copy()


            metadata["document"] = (
                chunk["document"]
            )


            metadatas.append(
                metadata
            )



        collection.add(

            ids=ids,

            documents=documents,

            embeddings=embeddings,

            metadatas=metadatas

        )



        return collection.count()



if __name__ == "__main__":


    store = PersonalStore()



    chunks = store.load_embeddings(
        "data/personal_docs/"
        "A5.16.03_embeddings.json"
    )


    count = store.insert_chunks(

        collection_name=
            "personal_A5_16_03",

        chunks=chunks

    )


    print(
        "Inserted vectors:",
        count
    )