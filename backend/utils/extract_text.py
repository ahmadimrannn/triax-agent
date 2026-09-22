from io import BytesIO

from docx import Document
from pypdf import PdfReader


def extract_text(file_bytes: bytes, filename: str) -> str:
    extension = filename.lower().rsplit(".", 1)[-1]

    if extension == "txt":
        return file_bytes.decode("utf-8")

    if extension == "pdf":
        reader = PdfReader(BytesIO(file_bytes))

        text = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                text.append(page_text)

        return "\n".join(text)

    if extension == "docx":
        document = Document(BytesIO(file_bytes))

        return "\n".join(
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        )

    raise ValueError(
        f"Unsupported file type: .{extension}. "
        "Supported types: .txt, .pdf, .docx"
    )
