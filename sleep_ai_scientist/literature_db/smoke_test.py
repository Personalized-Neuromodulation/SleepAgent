"""Legacy query constants retained without implementing live API smoke tests."""

BASE_QUERY = (
    '("sleep deprivation" OR "total sleep deprivation" OR "sleep restriction") '
    'AND ("functional connectivity" OR "resting-state fMRI" OR '
    '"resting state fMRI" OR "rs-fMRI")'
)
PROVIDERS = ("pubmed", "europe_pmc", "openalex", "semantic_scholar")


def provider_query(provider: str, current_year: int) -> str:
    if provider == "pubmed":
        return (
            f'({BASE_QUERY}) AND (humans[MeSH Terms]) AND (english[Language]) '
            f'AND ("2016/01/01"[Date - Publication] : '
            f'"{current_year}/12/31"[Date - Publication])'
        )
    if provider == "europe_pmc":
        return f"({BASE_QUERY}) AND LANG:eng AND FIRST_PDATE:[2016-01-01 TO {current_year}-12-31]"
    if provider == "openalex":
        return f"{BASE_QUERY} human 2016-{current_year}"
    return f"{BASE_QUERY} human 2016 {current_year}"
