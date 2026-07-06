import importlib.util
from pathlib import Path

module_path = Path(__file__).resolve().parents[1] / "data-engineering" / "models.py"
spec = importlib.util.spec_from_file_location("data_engineering_models", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

Base = module.Base
Document = module.Document
Page = module.Page
Paragraph = module.Paragraph
CleanedCsvRecord = module.CleanedCsvRecord
Ticket = module.Ticket

__all__ = ["Base", "Document", "Page", "Paragraph", "CleanedCsvRecord", "Ticket"]
