from __future__ import annotations
from dataclasses import dataclass,field
from datetime import date
from typing import Any,Protocol
from .target_journals import TargetJournal

@dataclass
class JournalDiscoveryResult:
    candidates:list[Any]=field(default_factory=list);next_cursor:str|None=None;statistics:dict[str,Any]=field(default_factory=dict);warnings:list[str]=field(default_factory=list);errors:list[str]=field(default_factory=list)
class JournalDiscoveryProvider(Protocol):
    name:str
    def discover(self,journal:TargetJournal,start_date:date,end_date:date,cursor:str|None=None)->JournalDiscoveryResult:...

def journal_query_key(journal:TargetJournal)->tuple[str,str]:
    if journal.issn:return "issn",journal.issn
    if journal.eissn:return "eissn",journal.eissn
    return "journal_title",journal.title

def scan_journals(provider,journals,start_date,end_date,cursors=None):
    results={};cursors=cursors or {}
    for journal in journals:
        try:results[journal.journal_key]=provider.discover(journal,start_date,end_date,cursors.get(journal.journal_key))
        except Exception as exc:results[journal.journal_key]=JournalDiscoveryResult(errors=[str(exc)],statistics={"status":"failed"})
    return results
