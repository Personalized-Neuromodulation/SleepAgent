from __future__ import annotations
import hashlib,os,shutil,tempfile
from pathlib import Path
from sqlalchemy import select
from .models import FulltextDocument,Paper,utcnow

class PDFValidationError(ValueError):
    def __init__(self,code,message):super().__init__(message);self.code=code

def validate_pdf(data:bytes,min_size=32):
    if not data:raise PDFValidationError("EMPTY_RESPONSE","empty PDF")
    if not data.startswith(b"%PDF-"):
        code="HTML_INSTEAD_OF_PDF" if b"<html" in data[:512].lower() else "INVALID_PDF_HEADER"
        raise PDFValidationError(code,"content is not a PDF")
    if len(data)<min_size:raise PDFValidationError("CORRUPTED_PDF","PDF below minimum size")
    return hashlib.sha256(data).hexdigest()

class PDFStorage:
    def __init__(self,root,quarantine,min_size=32):self.root=Path(root);self.quarantine=Path(quarantine);self.min_size=min_size
    def import_pdf(self,session,pdf,paper_id=None,doi=None,pmid=None):
        from .models import PaperIdentifier
        paper=session.get(Paper,paper_id) if paper_id else None
        kind,value=("doi",doi) if doi else ("pmid",pmid)
        if not paper and value:
            from .normalization import normalize_doi,normalize_pmid
            normalized=normalize_doi(value) if kind=="doi" else normalize_pmid(value);ident=session.scalar(select(PaperIdentifier).where(PaperIdentifier.identifier_type==kind,PaperIdentifier.normalized_value==normalized));paper=session.get(Paper,ident.paper_id) if ident else None
        src=Path(pdf)
        if not paper:
            self.quarantine.mkdir(parents=True,exist_ok=True);target=self.quarantine/src.name
            if src.exists() and src.resolve()!=target.resolve():shutil.copy2(src,target)
            raise LookupError("Paper does not exist; no canonical paper was created")
        data=src.read_bytes();digest=validate_pdf(data,self.min_size);existing=session.scalar(select(FulltextDocument).where(FulltextDocument.paper_id==paper.paper_id,FulltextDocument.content_hash==digest))
        if existing:return existing
        directory=self.root/paper.paper_id;directory.mkdir(parents=True,exist_ok=True);target=directory/f"{digest[:16]}.pdf"
        fd,tmp=tempfile.mkstemp(dir=directory,suffix=".tmp")
        try:
            with os.fdopen(fd,"wb") as f:f.write(data);f.flush();os.fsync(f.fileno())
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        relative=target.relative_to(self.root.parent)
        doc=FulltextDocument(paper_id=paper.paper_id,acquisition_method="manual",source_name="manual",local_relative_path=str(relative),original_filename=src.name,content_hash=digest,file_size=len(data),mime_type="application/pdf",validation_status="valid",is_open_access=None,imported_at=utcnow());session.add(doc);paper.fulltext_status="manual_pdf_available";session.flush();return doc
