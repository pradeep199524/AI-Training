from sqlalchemy import Column, Integer, String, ForeignKey, Text, Index, DateTime
from sqlalchemy.sql import func
# 1. Import JSONB specifically for PostgreSQL features
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Document(Base):
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True)
    filename = Column(String, unique=True, nullable=False)

    pages = relationship("Page", back_populates="document", cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = 'pages'

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    page_number = Column(Integer, nullable=False)

    # 2. Change Column from JSON to JSONB
    raw_json_content = Column(JSONB, nullable=False)

    document = relationship("Document", back_populates="pages")
    paragraphs = relationship("Paragraph", back_populates="page", cascade="all, delete-orphan")


class Paragraph(Base):
    __tablename__ = 'paragraphs'

    id = Column(Integer, primary_key=True)
    page_id = Column(Integer, ForeignKey('pages.id', ondelete='CASCADE'), nullable=False)
    paragraph_index = Column(Integer, nullable=False)
    text_content = Column(Text, nullable=False)

    page = relationship("Page", back_populates="paragraphs")


class CleanedCsvRecord(Base):
    __tablename__ = 'cleaned_csv_records'

    id = Column(Integer, primary_key=True)
    source_csv = Column(String, nullable=False)

    # 2. Change Column from JSON to JSONB
    row_data = Column(JSONB, nullable=False)


class Ticket(Base):
    __tablename__ = 'tickets'

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    customer_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default='new')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# --- Basic Indexing Setup ---
Index('ix_pages_raw_json', Page.raw_json_content, postgresql_using='gin')
Index('ix_csv_row_data', CleanedCsvRecord.row_data, postgresql_using='gin')