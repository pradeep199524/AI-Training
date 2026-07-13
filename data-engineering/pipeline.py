import os
import logging
import json
import gc
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
    
    if not os.path.exists(pdf_path):
        logging.error(f"File skipped. Path does not exist: {pdf_path}")
        return False

    try:
        logging.info(f"Starting parsing execution for: {pdf_filename}")
        
        # Clear existing entries to prevent duplicate primary keys
        existing_doc = session.query(Document).filter_by(filename=pdf_filename).first()
        if existing_doc:
            session.delete(existing_doc)
            session.flush()

        db_doc = Document(filename=pdf_filename)
        session.add(db_doc)
        session.flush()

        with pdfplumber.open(pdf_path) as pdf:
            for idx, page in enumerate(pdf.pages):
                
                # 1. Table Bounding Boxes identification
                table_objects = page.find_tables()
                table_bboxes = [t.bbox for t in table_objects]
                tables_data = page.extract_tables()

                def is_char_in_table(c):
                    x0, top, x1, bottom = c["x0"], c["top"], c["x1"], c["bottom"]
                    for bbox in table_bboxes:
                        b_x0, b_top, b_x1, b_bottom = bbox
                        if not (x1 < b_x0 or x0 > b_x1 or bottom < b_top or top > b_bottom):
                            return True
                    return False

                # Filter out tables completely to avoid line pollution
                clean_page = page.filter(lambda obj: obj.get("object_type") == "char" and not is_char_in_table(obj))
                text = clean_page.extract_text()
                
                raw_lines = text.split('\n') if text else []
                
                sections = []
                current_header = "Visual Header Block"
                current_paragraph_lines = []
                
                # 2. Smart Buffer Flow: Reconstructing complete text flows
                for line in raw_lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Detect if line is a Header
                    is_header = False
                    first_token = line.split(' ')[0]
                    
                    if (first_token.replace('.', '').isdigit() and len(line) < 100) or line.endswith(':') or (line.isupper() and len(line) < 60):
                        is_header = True

                    if is_header:
                        if current_paragraph_lines:
                            full_para_text = " ".join(current_paragraph_lines)
                            sections.append({"header": current_header, "text": full_para_text})
                            current_paragraph_lines = []
                        current_header = line
                    else:
                        current_paragraph_lines.append(line)
                        
                        if line.endswith(('.', '?', '!')):
                            full_para_text = " ".join(current_paragraph_lines)
                            sections.append({"header": current_header, "text": full_para_text})
                            current_paragraph_lines = []

                if current_paragraph_lines:
                    full_para_text = " ".join(current_paragraph_lines)
                    sections.append({"header": current_header, "text": full_para_text})

                # 3. Save Clean Normalized JSON
                normalized_page_json = {
                    "page_number": idx + 1,
                    "content_blocks": sections, 
                    "tables": tables_data
                }

                db_page = Page(
                    document_id=db_doc.id,
                    page_number=idx + 1,
                    raw_json_content=normalized_page_json
                )
                session.add(db_page)
                session.flush()

                # 4. Save to Relational Paragraph Table
                for p_idx, block in enumerate(sections):
                    combined_content = f"[{block['header']}] {block['text']}" if block['header'] != "Visual Header Block" else block['text']
                    
                    db_para = Paragraph(
                        page_id=db_page.id,
                        paragraph_index=p_idx,
                        text_content=combined_content
                    )
                    session.add(db_para)

                # --- BATCH PROCESSING START ---
                # Every 10 pages, commit to DB and force memory cleanup
                if (idx + 1) % 10 == 0:
                    session.commit()
                    gc.collect()
                    logging.info(f"Batch checkpoint: Committed pages up to {idx + 1}")
                # --- BATCH PROCESSING END ---
                    
        session.commit()
        logging.info(f"Successfully committed document: {pdf_filename}")
        return True

    except Exception as e:
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