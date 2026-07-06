import os
import logging
import json
import pandas as pd
import pdfplumber
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Document, Page, Paragraph, CleanedCsvRecord

# 1. Load Environment Configurations cleanly from .env file
from dotenv import load_dotenv
load_dotenv()

# 2. Pipeline Fault Tolerance & Logging Setup
logging.basicConfig(
    filename='pipeline.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s] - %(message)s'
)

# 3. Securely Fetch Database Credentials from Environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    critical_error = "CRITICAL: DATABASE_URL variable not set in the active configuration environment (.env file)."
    logging.critical(critical_error)
    raise ValueError(critical_error)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def process_pdf(pdf_filename, session):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(base_dir, "data", pdf_filename)
    
    # Check for missing file error gracefully
    if not os.path.exists(pdf_path):
        logging.error(f"File skipped. Path does not exist: {pdf_path}")
        return False

    try:
        logging.info(f"Starting parsing execution for: {pdf_filename}")
        
        # Check if document already tracked to prevent duplicates
        existing_doc = session.query(Document).filter_by(filename=pdf_filename).first()
        if existing_doc:
            session.delete(existing_doc)  # Overwrite refresh
            session.flush()

        db_doc = Document(filename=pdf_filename)
        session.add(db_doc)
        session.flush()

        with pdfplumber.open(pdf_path) as pdf:
            for idx, page in enumerate(pdf.pages):
                text = page.extract_text()
                lines = text.split('\n') if text else []
                
                sections = []
                current_section = {"header": "Visual Header Block", "paragraphs": []}
                
                # Layout Boundary and Hierarchy Extraction
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    first_token = line.split(' ')[0]
                    if first_token.replace('.', '').isdigit() and len(line) < 120:
                        if current_section["paragraphs"]:
                            sections.append(current_section)
                        current_section = {"header": line, "paragraphs": []}
                    else:
                        current_section["paragraphs"].append(line)
                if current_section["paragraphs"]:
                    sections.append(current_section)

                # Normalize layout data structure directly to JSON
                normalized_page_json = {
                    "page_number": idx + 1,
                    "sections": sections,
                    "tables": page.extract_tables()
                }

                db_page = Page(
                    document_id=db_doc.id,
                    page_number=idx + 1,
                    raw_json_content=normalized_page_json
                )
                session.add(db_page)
                session.flush()

                # Granular paragraph level extraction tracking for precise traceability
                p_idx = 0
                for sec in sections:
                    for para_text in sec["paragraphs"]:
                        db_para = Paragraph(
                            page_id=db_page.id,
                            paragraph_index=p_idx,
                            text_content=para_text
                        )
                        session.add(db_para)
                        p_idx += 1
                        
        logging.info(f"Successfully committed document: {pdf_filename}")
        return True

    except Exception as e:
        # Handle partial failures gracefully: Log error, rollback session, and continue batch
        logging.error(f"Partial failure processing PDF '{pdf_filename}': {str(e)}")
        session.rollback()
        return False

def process_csv(csv_filename, session):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "data", csv_filename)
    
    if not os.path.exists(csv_path):
        logging.error(f"File skipped. Path does not exist: {csv_path}")
        return False

    try:
        logging.info(f"Profiling records for file: {csv_filename}")
        df = pd.read_csv(csv_path)
        
        # Enforce quality logic: Clean anomalies and invalid fields
        if 'id' in df.columns:
            df = df.dropna(subset=['id'])
        elif 'ID' in df.columns:
            df = df.dropna(subset=['ID'])
        if 'email' in df.columns:
            df['email'] = df['email'].astype(str).str.strip()
            
        # Clear existing records for this file to keep data idempotent
        session.query(CleanedCsvRecord).filter_by(source_csv=csv_filename).delete()

        # Remove existing Document entry for this CSV to keep document listing idempotent
        existing_doc = session.query(Document).filter_by(filename=csv_filename).first()
        if existing_doc:
            session.delete(existing_doc)
            session.flush()

        for _, row in df.iterrows():
            # Convert row to dictionary
            raw_dict = row.to_dict()
            
            # 🔥 BULLETPROOF FIX: Scrub all NaN values out of the dictionary values
            clean_dict = {
                k: (None if pd.isna(v) else v) 
                for k, v in raw_dict.items()
            }
            
            record = CleanedCsvRecord(
                source_csv=csv_filename,
                row_data=clean_dict
            )
            session.add(record)
            
        # Create a lightweight Document record for CSV files so they appear in document listings
        try:
            csv_doc = Document(filename=csv_filename)
            session.add(csv_doc)
            session.flush()
        except Exception as e:
            logging.warning(f"Could not create document record for CSV '{csv_filename}': {str(e)}")

        logging.info(f"Successfully processed CSV dataset: {csv_filename}")
        return True
    except Exception as e:
        logging.error(f"Partial failure parsing CSV '{csv_filename}': {str(e)}")
        session.rollback()
        return False

def run_pipeline():
    # Construct Schema Definitions
    Base.metadata.create_all(engine)
    session = SessionLocal()
    
    # Target batch lists - Updated for complex production file mapping
    target_pdfs = ["2606.25924v1.pdf", "2606.25956v1.pdf", "2606.25959v1.pdf"]
    target_csvs = ["MOCK_DATA.csv", "production_customer_feeds.csv"]
    
    # Execute loops
    for pdf in target_pdfs:
        process_pdf(pdf, session)
        
    # Execute loops for all Tabular CSV datasets
    for csv_file in target_csvs:
        process_csv(csv_file, session)
    
    session.commit()
    session.close()
    print("🚀 Pipeline Execution Finished! Check 'pipeline.log' for diagnostics.")

if __name__ == "__main__":
    run_pipeline()