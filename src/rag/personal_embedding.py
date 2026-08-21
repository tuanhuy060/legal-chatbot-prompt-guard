from pathlib import Path
import json
from sentence_transformers import SentenceTransformer
from tqdm import tqdm


class PersonalEmbedding:


    def __init__(
        self,
        model_name="BAAI/bge-m3"
    ):

        print(
            "Loading embedding model..."
        )

        self.model = SentenceTransformer(
            model_name
        )



    def load_chunks(
        self,
        file_path
    ):

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)



    def create_embeddings(
        self,
        chunks
    ):

        texts = []


        for chunk in chunks:

            texts.append(
                chunk["content"]
            )



        embeddings = self.model.encode(
            texts,
            batch_size=8,
            show_progress_bar=True,
            normalize_embeddings=True
        )



        for chunk, vector in zip(
            chunks,
            embeddings
        ):

            chunk["embedding"] = (
                vector.tolist()
            )



        return chunks



    def save(
        self,
        data,
        output_file
    ):

        with open(
            output_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )




if __name__ == "__main__":


    embedder = PersonalEmbedding()


    input_file = (
        "data/personal_docs/"
        "A5.16.03_chunks.json"
    )


    output_file = (
        "data/personal_docs/"
        "A5.16.03_embeddings.json"
    )



    chunks = embedder.load_chunks(
        input_file
    )



    result = embedder.create_embeddings(
        chunks
    )



    embedder.save(
        result,
        output_file
    )


    print(
        "Embedding completed:"
    )

    print(
        output_file
    )
