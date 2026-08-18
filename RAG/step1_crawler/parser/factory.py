# parser/factory.py

from .nature import NatureParser
from .science import ScienceParser
from .cell import CellParser
from .plos import PLOSParser
from .new_journal import NewJournalParser


def create_parser(
        journal_type,
        agent
):

    journal_type = journal_type.lower()


    PARSER_MAP = {

        "nature":
            NatureParser,

        "science":
            ScienceParser,

        "cell":
            CellParser,

        "plos":
            PLOSParser,
        "other": NewJournalParser

    }


    parser_cls = PARSER_MAP.get(
        journal_type.lower()
    )

    if not parser_cls:
        raise ValueError(
            f"No parser for {journal_type}"
        )

    return parser_cls(
        paper_agent=agent
    )
