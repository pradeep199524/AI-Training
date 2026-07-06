import os
import sys
import logging
from celery import Celery
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

# --- CRITICAL PATH BRIDGE ---
# Dynamically append the Module 1 folder into Python's path so we can import its execution functions
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(base_dir, "..", "data-engineering"))

from pipeline import process_pdf, process_csv

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL")

# Initialize Celery Worker Queue Instance
celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)

# --- FIXED LOGGING SIGNAL CONNECT ---
from celery.signals import setup_logging

@setup_logging.connect
def void_logging_setup(*args, **kwargs):
    pass
# ------------------------------------

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@celery_app.task(name="tasks.async_ingest_pdf")
def async_ingest_pdf(pdf_filename, correlation_id):
    logger = logging.getLogger("pipeline")
    logger.info(f"Worker pulled PDF ingestion job: {pdf_filename}", extra={"correlation_id": correlation_id})
    
    session = SessionLocal()
    try:
        success = process_pdf(pdf_filename, session)
        if success:
            session.commit()
            logger.info(f"Worker completed processing PDF successfully", extra={"correlation_id": correlation_id})
            return {"status": "success", "file": pdf_filename}
        else:
            logger.error(f"Worker processing engine reported failure", extra={"correlation_id": correlation_id})
            return {"status": "failed", "file": pdf_filename}
    except Exception as e:
        session.rollback()
        logger.error(f"Worker broke execution: {str(e)}", extra={"correlation_id": correlation_id})
        return {"status": "error", "reason": str(e)}
    finally:
        session.close()

@celery_app.task(name="tasks.async_ingest_csv")
def async_ingest_csv(csv_filename, correlation_id):
    logger = logging.getLogger("pipeline")
    logger.info(f"Worker pulled CSV ingestion job: {csv_filename}", extra={"correlation_id": correlation_id})
    
    session = SessionLocal()
    try:
        success = process_csv(csv_filename, session)
        if success:
            session.commit()
            logger.info(f"Worker completed processing CSV dataset successfully", extra={"correlation_id": correlation_id})
            return {"status": "success", "file": csv_filename}
        else:
            logger.error(f"Worker processing engine reported failure", extra={"correlation_id": correlation_id})
            return {"status": "failed", "file": csv_filename}
    except Exception as e:
        session.rollback()
        logger.error(f"Worker broke execution: {str(e)}", extra={"correlation_id": correlation_id})
        return {"status": "error", "reason": str(e)}
    finally:
        session.close()