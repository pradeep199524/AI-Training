import os
import sys
import uuid
import logging
import shutil

from fastapi import FastAPI, Request, Response, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(base_dir, "..", "data-engineering"))

from worker import async_ingest_pdf, async_ingest_csv, celery_app
from celery.result import AsyncResult
from pipeline import process_pdf, process_csv
from models import Base, Document, Ticket

load_dotenv()

logger = logging.getLogger("pipeline")
logger.setLevel(logging.INFO)
if not logger.handlers:
    log_handler = logging.FileHandler("pipeline.log")
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [ID: %(correlation_id)s] - %(message)s')
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

app = FastAPI(
    title="Data Engineering Microservice Framework",
    description="Module 2 API Engine exposing ingestion, traceability, and business record workflows.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base.metadata.create_all(engine)


class IngestionRequest(BaseModel):
    filename: str = Field(..., min_length=1, description="Target file name sitting inside data-engineering/data/")

    class Config:
        json_schema_extra = {
            "example": {"filename": "production_customer_feeds.csv"}
        }


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    customer_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    status: str = Field(default="new", max_length=50)


class TicketUpdate(TicketCreate):
    pass


@app.middleware("http")
async def add_correlation_id_and_logging(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.correlation_id = correlation_id
        return record

    logging.setLogRecordFactory(record_factory)

    logger.info(f"HTTP Request Picked Up: {request.method} {request.url.path}")
    response: Response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    logger.info(f"HTTP Response Generated. Status: {response.status_code}")
    return response


@app.post("/api/v1/ingest/pdf", status_code=status.HTTP_202_ACCEPTED, tags=["Queue Ingestion Triggers"])
async def trigger_pdf_ingestion(payload: IngestionRequest):
    correlation_id = str(uuid.uuid4())
    file_path = os.path.join(base_dir, "..", "data-engineering", "data", payload.filename)

    if not os.path.exists(file_path):
        logger.error(f"Ingestion Aborted. File not found at location: {payload.filename}")
        raise HTTPException(status_code=404, detail=f"Target file '{payload.filename}' not found.")

    task_id = None
    direct_ingest = False
    try:
        task = async_ingest_pdf.delay(payload.filename, correlation_id)
        task_id = task.id
        logger.info(f"Async PDF ingestion task context successfully handed off to Redis. Job ID: {task.id}")
        return {"status": "queued", "task_id": task.id, "message": "Background ingestion process initialized successfully."}
    except Exception as exc:
        logger.warning(f"Redis unavailable for PDF ingestion. Falling back to direct ingestion for {payload.filename}. Error: {str(exc)}")
        direct_ingest = True
        session = SessionLocal()
        try:
            success = process_pdf(payload.filename, session)
            if not success:
                session.rollback()
                raise HTTPException(status_code=500, detail=f"Direct ingestion failed for {payload.filename}")
            session.commit()
            logger.info(f"Direct PDF ingestion completed for {payload.filename}")
            return {"status": "processed", "task_id": task_id, "direct_ingest": True, "message": "File ingested directly because background queue was unavailable."}
        except HTTPException:
            raise
        except Exception as exc:
            session.rollback()
            logger.error(f"Direct PDF ingestion failed for {payload.filename}: {str(exc)}")
            raise HTTPException(status_code=500, detail=f"Direct ingestion failed for {payload.filename}") from exc
        finally:
            session.close()


@app.post("/api/v1/ingest/csv", status_code=status.HTTP_202_ACCEPTED, tags=["Queue Ingestion Triggers"])
async def trigger_csv_ingestion(payload: IngestionRequest):
    correlation_id = str(uuid.uuid4())
    file_path = os.path.join(base_dir, "..", "data-engineering", "data", payload.filename)

    if not os.path.exists(file_path):
        logger.error(f"Ingestion Aborted. File not found at location: {payload.filename}")
        raise HTTPException(status_code=404, detail=f"Target file '{payload.filename}' not found.")

    task_id = None
    direct_ingest = False
    try:
        task = celery_app.send_task("tasks.async_ingest_csv", args=[payload.filename, correlation_id])
        task_id = task.id
        logger.info(f"Async CSV ingestion task context successfully handed off to Redis. Job ID: {task.id}")
        return {"status": "queued", "task_id": task.id, "message": "Background ingestion process initialized successfully."}
    except Exception as exc:
        logger.warning(f"Redis unavailable for CSV ingestion. Falling back to direct ingestion for {payload.filename}. Error: {str(exc)}")
        direct_ingest = True
        session = SessionLocal()
        try:
            success = process_csv(payload.filename, session)
            if not success:
                session.rollback()
                raise HTTPException(status_code=500, detail=f"Direct ingestion failed for {payload.filename}")
            session.commit()
            logger.info(f"Direct CSV ingestion completed for {payload.filename}")
            return {"status": "processed", "task_id": task_id, "direct_ingest": True, "message": "File ingested directly because background queue was unavailable."}
        except HTTPException:
            raise
        except Exception as exc:
            session.rollback()
            logger.error(f"Direct CSV ingestion failed for {payload.filename}: {str(exc)}")
            raise HTTPException(status_code=500, detail=f"Direct ingestion failed for {payload.filename}") from exc
        finally:
            session.close()


@app.get("/", tags=["System"])
async def health_check():
    return {"status": "online", "message": "Backend API Engine is running."}


@app.get("/api/v1/documents", tags=["Data Engine Lookups"])
async def list_documents(limit: int = 20):
    session = SessionLocal()
    try:
        # 1. Fetch the PDF data array so the document browser doesn't break
        docs = session.query(Document).order_by(Document.id.desc()).limit(limit).all()
        payload = [
            {
                "id": doc.id,
                "filename": doc.filename,
                "page_count": len(doc.pages),
                "paragraph_count": sum(len(page.paragraphs) for page in doc.pages),
            }
            for doc in docs
        ]
        
        # 2. Derive the KPI badge number from the actual physical directory
        data_dir = os.path.join(base_dir, "..", "data-engineering", "data")
        total_uploaded_files = 0
        
        if os.path.exists(data_dir):
            total_uploaded_files = len([
                f for f in os.listdir(data_dir)
                if f.lower().endswith(('.pdf', '.csv')) and os.path.isfile(os.path.join(data_dir, f))
            ])
        else:
            total_uploaded_files = len(payload) # Fallback baseline
            
        # Return total files for the badge, but preserve data rows for the list views
        return {"count": total_uploaded_files, "data": payload}
        
    except Exception as exc:
        logger.error(f"Document lookup failed: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to retrieve document metadata.") from exc
    finally:
        session.close()


@app.get("/api/v1/files", tags=["System"])
async def list_available_files(extensions: str = "pdf,csv"):
    """List available files in the data-engineering/data directory.

    Query param `extensions` is a comma-separated list, e.g. `pdf,csv`.
    """
    try:
        exts = [e.strip().lower() for e in extensions.split(',') if e.strip()]
        data_dir = os.path.join(base_dir, "..", "data-engineering", "data")
        files = []
        if os.path.exists(data_dir):
            for fname in os.listdir(data_dir):
                if any(fname.lower().endswith('.' + e) for e in exts):
                    files.append(fname)
        files.sort()
        return {"count": len(files), "data": files}
    except Exception as exc:
        logger.error(f"Available files lookup failed: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to list available files.") from exc


@app.get("/api/v1/documents/{document_id}", tags=["Data Engine Lookups"])
async def get_document(document_id: int):
    session = SessionLocal()
    try:
        doc = session.get(Document, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        payload = {
            "id": doc.id,
            "filename": doc.filename,
            "pages": [
                {"id": page.id, "page_number": page.page_number, "paragraph_count": len(page.paragraphs)}
                for page in doc.pages
            ],
        }
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Document detail lookup failed: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to retrieve document details.") from exc
    finally:
        session.close()


@app.get("/api/v1/records/csv", tags=["Data Engine Lookups"])
async def fetch_csv_records(source_file: str = None, limit: int = 10):
    session = SessionLocal()
    try:
        if source_file:
            query = text("SELECT id, source_csv, row_data FROM cleaned_csv_records WHERE source_csv = :src LIMIT :lim;")
            result = session.execute(query, {"src": source_file, "lim": limit}).fetchall()
        else:
            query = text("SELECT id, source_csv, row_data FROM cleaned_csv_records LIMIT :lim;")
            result = session.execute(query, {"lim": limit}).fetchall()

        return {"count": len(result), "data": [{"id": r[0], "source": r[1], "row": r[2]} for r in result]}
    except Exception as exc:
        logger.error(f"Storage access error: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to retrieve database records.") from exc
    finally:
        session.close()


@app.get("/api/v1/records/pdf", tags=["Data Engine Lookups"])
async def fetch_pdf_records(source_file: str = None, limit: int = 10):
    session = SessionLocal()
    try:
        if source_file:
            query = text("""
                SELECT d.filename, p.page_number, para.paragraph_index, para.text_content
                FROM paragraphs para
                JOIN pages p ON para.page_id = p.id
                JOIN documents d ON p.document_id = d.id
                WHERE d.filename = :src AND para.text_content != ''
                ORDER BY p.page_number ASC, para.paragraph_index ASC
                LIMIT :lim;
            """)
            result = session.execute(query, {"src": source_file, "lim": limit}).fetchall()
        else:
            query = text("""
                SELECT d.filename, p.page_number, para.paragraph_index, para.text_content
                FROM paragraphs para
                JOIN pages p ON para.page_id = p.id
                JOIN documents d ON p.document_id = d.id
                WHERE para.text_content != ''
                LIMIT :lim;
            """)
            result = session.execute(query, {"lim": limit}).fetchall()

        trace_tree = [{"source_pdf": r[0], "page": r[1], "paragraph_index": r[2], "text": r[3]} for r in result]
        return {"count": len(trace_tree), "data": trace_tree}
    except Exception as exc:
        logger.error(f"PDF trace retrieval failure: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to retrieve database PDF paragraphs.") from exc
    finally:
        session.close()


@app.get("/api/v1/tickets", tags=["Business Records"])
async def list_tickets():
    session = SessionLocal()
    try:
        tickets = session.query(Ticket).order_by(Ticket.id.desc()).all()
        payload = [
            {
                "id": ticket.id,
                "title": ticket.title,
                "customer_name": ticket.customer_name,
                "description": ticket.description,
                "status": ticket.status,
            }
            for ticket in tickets
        ]
        return {"count": len(payload), "data": payload}
    except Exception as exc:
        logger.error(f"Ticket listing failed: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to retrieve tickets.") from exc
    finally:
        session.close()


@app.post("/api/v1/tickets", status_code=status.HTTP_201_CREATED, tags=["Business Records"])
async def create_ticket(payload: TicketCreate):
    session = SessionLocal()
    try:
        ticket = Ticket(**payload.model_dump())
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        return {
            "id": ticket.id,
            "title": ticket.title,
            "customer_name": ticket.customer_name,
            "description": ticket.description,
            "status": ticket.status,
        }
    except Exception as exc:
        session.rollback()
        logger.error(f"Ticket creation failed: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to create ticket.") from exc
    finally:
        session.close()


@app.put("/api/v1/tickets/{ticket_id}", tags=["Business Records"])
async def update_ticket(ticket_id: int, payload: TicketUpdate):
    session = SessionLocal()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        for key, value in payload.model_dump().items():
            setattr(ticket, key, value)

        session.commit()
        session.refresh(ticket)
        return {
            "id": ticket.id,
            "title": ticket.title,
            "customer_name": ticket.customer_name,
            "description": ticket.description,
            "status": ticket.status,
        }
    except HTTPException:
        raise
    except Exception as exc:
        session.rollback()
        logger.error(f"Ticket update failed: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to update ticket.") from exc
    finally:
        session.close()


@app.delete("/api/v1/records/csv/{record_id}", tags=["Data Engine Lookups"])
async def delete_csv_record(record_id: int):
    session = SessionLocal()
    try:
        query = text("DELETE FROM cleaned_csv_records WHERE id = :id;")
        result = session.execute(query, {"id": record_id})
        session.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        logger.info(f"Record {record_id} deleted successfully.")
        return {"status": "success", "message": f"Record {record_id} deleted."}
    except Exception as exc:
        session.rollback()
        logger.error(f"Storage deletion error: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to delete database record.") from exc
    finally:
        session.close()


@app.delete("/api/v1/tickets/{ticket_id}", tags=["Business Records"])
async def delete_ticket(ticket_id: int):
    session = SessionLocal()
    try:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        session.delete(ticket)
        session.commit()
        return {"status": "success", "message": f"Ticket {ticket_id} deleted."}
    except HTTPException:
        raise
    except Exception as exc:
        session.rollback()
        logger.error(f"Ticket deletion failed: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to delete ticket.") from exc
    finally:
        session.close()


@app.post("/api/v1/upload/file")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required")

    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in {".pdf", ".csv"}:
        raise HTTPException(status_code=400, detail="Only .pdf and .csv files are supported")

    save_path = os.path.join(base_dir, "..", "data-engineering", "data", file.filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    correlation_id = str(uuid.uuid4())
    task_id = None
    direct_ingest = False
    try:
        if extension == ".pdf":
            task = async_ingest_pdf.delay(file.filename, correlation_id)
        else:
            task = async_ingest_csv.delay(file.filename, correlation_id)
        task_id = task.id
        logger.info(f"Triggered ingestion for {file.filename}. Task ID: {task.id}")
    except Exception as exc:
        logger.warning(f"Background queue unavailable for {file.filename}. Falling back to direct ingestion. Error: {str(exc)}")
        direct_ingest = True
        session = SessionLocal()
        try:
            if extension == ".pdf":
                success = process_pdf(file.filename, session)
            else:
                success = process_csv(file.filename, session)
            if not success:
                session.rollback()
                raise HTTPException(status_code=500, detail=f"Direct ingestion failed for {file.filename}")
            session.commit()
            logger.info(f"Direct ingestion completed for {file.filename}")
        except HTTPException:
            raise
        except Exception as exc:
            session.rollback()
            logger.error(f"Direct ingestion failed for {file.filename}: {str(exc)}")
            raise HTTPException(status_code=500, detail=f"Direct ingestion failed for {file.filename}") from exc
        finally:
            session.close()

    response = {
        "filename": file.filename,
        "message": "File uploaded and ingestion started successfully",
        "task_id": task_id,
        "direct_ingest": direct_ingest,
    }
    if direct_ingest:
        response["message"] = "File uploaded and ingested directly because background queue was unavailable."
    return response


@app.get("/api/v1/tasks/{task_id}", tags=["System"])
async def get_task_status(task_id: str):
    try:
        result = AsyncResult(task_id, app=celery_app)
        state = result.state
        payload = {"task_id": task_id, "status": state}
        # include result if available and safe
        if state == 'SUCCESS':
            try:
                payload["result"] = result.result
            except Exception:
                payload["result"] = None
        elif state in ('FAILURE', 'REVOKED'):
            try:
                payload["result"] = str(result.result)
            except Exception:
                payload["result"] = None
        return payload
    except Exception as exc:
        logger.error(f"Task status lookup failed: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to retrieve task status.") from exc

@app.delete("/api/v1/files/{filename}", tags=["System", "Data Engine Lookups"])
async def delete_document_and_file(filename: str):
    session = SessionLocal()
    try:
        # 1. Remove the physical file from the data directory
        file_path = os.path.join(base_dir, "..", "data-engineering", "data", filename)
        file_deleted = False
        
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted physical file: {file_path}")
            file_deleted = True

        # 2. Clean up PDF records from the database
        doc = session.query(Document).filter(Document.filename == filename).first()
        if doc:
            session.delete(doc) # This will cascade and delete pages/paragraphs if relationships are configured
            logger.info(f"Deleted database document records for: {filename}")
        
        # 3. Clean up CSV records from the database
        if filename.lower().endswith('.csv'):
            query_csv = text("DELETE FROM cleaned_csv_records WHERE source_csv = :fname;")
            session.execute(query_csv, {"fname": filename})
            logger.info(f"Deleted database CSV records for: {filename}")

        session.commit()

        if not file_deleted and not doc:
            raise HTTPException(status_code=404, detail="File or Document not found.")

        return {"status": "success", "message": f"Successfully deleted {filename} and its extracted data."}
        
    except HTTPException:
        raise
    except Exception as exc:
        session.rollback()
        logger.error(f"File deletion error for {filename}: {str(exc)}")
        raise HTTPException(status_code=500, detail="Unable to delete file and data.") from exc
    finally:
        session.close()