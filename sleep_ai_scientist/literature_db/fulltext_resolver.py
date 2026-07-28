from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

RETRYABLE={"RATE_LIMITED_429","SERVER_ERROR_5XX","TIMEOUT","CONNECTION_ERROR","EMPTY_RESPONSE"}
@dataclass
class ResolvedFulltext: source_url:str;resolver_name:str;license:str|None=None;is_open_access:bool=True
class FulltextResolver(Protocol):
    def resolve(self,paper,identifiers)->ResolvedFulltext|None:...
class EuropePMCOAResolver:
    name="europe_pmc_oa"
    def resolve(self,paper,identifiers):
        pmcid=identifiers.get("pmcid");return ResolvedFulltext(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextPDF",self.name) if pmcid else None
class DirectOpenPDFResolver:
    name="direct_open_pdf"
    def resolve(self,paper,identifiers):
        url=identifiers.get("open_pdf_url");return ResolvedFulltext(url,self.name) if url and url.startswith("https://") else None
