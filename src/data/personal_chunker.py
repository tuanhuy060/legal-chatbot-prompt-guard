import re
import json
import uuid
from pathlib import Path


class PersonalChunker:


    def __init__(
        self,
        max_chars=1500
    ):

        self.max_chars = max_chars



    # ======================
    # Load markdown
    # ======================

    def load_markdown(
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

            return f.read()



    # ======================
    # Extract metadata
    # ======================

    def extract_metadata(
        self,
        markdown
    ):

        metadata = {

            "document_type":
                "unknown",

            "category":
                "unknown",

            "domain":
                "unknown"

        }


        patterns = {

            "document_type":
                r"DOCUMENT_TYPE:\s*(.*)",

            "category":
                r"CATEGORY:\s*(.*)",

            "domain":
                r"DOMAIN:\s*(.*)"

        }



        for key, pattern in patterns.items():

            match = re.search(
                pattern,
                markdown
            )


            if match:

                metadata[key] = (
                    match.group(1)
                    .strip()
                )


        return metadata



    # ======================
    # Remove markdown metadata
    # ======================

    def clean_markdown(
        self,
        markdown
    ):

        return re.sub(
            r"<!--.*?-->",
            "",
            markdown,
            flags=re.DOTALL
        )



    # ======================
    # Detect sections
    # ======================

    def split_sections(
        self,
        markdown
    ):


        pattern = (
            r"(?=##\s)"
        )


        sections = re.split(
            pattern,
            markdown
        )


        result = []


        current_section = (
            "THÔNG TIN CHUNG"
        )


        for section in sections:


            text = section.strip()


            if not text:

                continue



            title = current_section


            heading = re.search(
                r"##\s*(.*)",
                text
            )


            if heading:

                title = (
                    heading.group(1)
                    .strip()
                )


            if (
                "BIÊN NHẬN"
                in text.upper()
            ):

                section_type = (
                    "payment"
                )


            elif title.startswith(
                "ĐIỀU"
            ):

                section_type = (
                    "clause"
                )


            else:

                section_type = (
                    "intro"
                )


            result.append(
                {
                    "title": title,

                    "type": section_type,

                    "content": text

                }
            )


        return result



    # ======================
    # Split long section
    # ======================

    def split_long_text(
        self,
        section
    ):


        text = section["content"]


        if len(text) <= self.max_chars:

            return [
                text
            ]



        chunks = []

        current = ""



        for line in text.split("\n"):


            line = line.strip()


            if not line:

                continue



            if (
                len(current)
                +
                len(line)
                <=
                self.max_chars
            ):

                current += (
                    "\n\n"
                    +
                    line
                )


            else:

                chunks.append(
                    current.strip()
                )

                current = line



        if current:

            chunks.append(
                current.strip()
            )


        return chunks



    # ======================
    # Create chunks
    # ======================

    def create_chunks(
        self,
        markdown,
        document_name
    ):


        doc_metadata = (
            self.extract_metadata(
                markdown
            )
        )


        markdown = (
            self.clean_markdown(
                markdown
            )
        )


        sections = (
            self.split_sections(
                markdown
            )
        )


        chunks = []



        for section in sections:


            parts = (
                self.split_long_text(
                    section
                )
            )


            for index, part in enumerate(parts):


                chunks.append(
                    {

                        "chunk_id":
                            str(uuid.uuid4()),


                        "document":
                            document_name,


                        "type":
                            section["type"],


                        "content":
                            part,


                        "metadata":
                        {

                            "section":
                                section["title"],


                            "part":
                                index + 1,


                            **doc_metadata,


                            "source_type":
                                "personal_document"

                        }

                    }
                )



        return chunks



    # ======================
    # Save
    # ======================

    def save_chunks(
        self,
        chunks,
        output_file
    ):


        with open(
            output_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                chunks,
                f,
                ensure_ascii=False,
                indent=2
            )





if __name__ == "__main__":


    chunker = PersonalChunker()


    md = chunker.load_markdown(
        "data/personal_docs/A5.16.03.md"
    )


    chunks = chunker.create_chunks(
        md,
        "A5.16.03.docx"
    )


    output = (
        "data/personal_docs/"
        "A5.16.03_chunks.json"
    )


    chunker.save_chunks(
        chunks,
        output
    )


    print(
        f"Created {len(chunks)} chunks"
    )

    print(output)