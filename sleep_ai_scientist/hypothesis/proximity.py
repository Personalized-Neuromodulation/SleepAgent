from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import write_csv, write_json
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, HypothesisVariables, ProximityCluster


def hypothesis_from_dict(payload: dict[str, Any]) -> HypothesisRecord:
    payload = dict(payload)
    if isinstance(payload.get("variables"), dict):
        payload["variables"] = HypothesisVariables(**payload["variables"])
    return HypothesisRecord(**payload)


def hypothesis_text(hypothesis: HypothesisRecord) -> str:
    variables = hypothesis.variables.independent + hypothesis.variables.dependent + hypothesis.variables.covariates
    return " ".join([hypothesis.title, hypothesis.mechanism, hypothesis.primary_prediction, " ".join(variables)]).lower()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def tfidf_embeddings(hypotheses: list[HypothesisRecord]) -> tuple[list[str], dict[str, dict[str, float]]]:
    docs = [_tokens(hypothesis_text(item)) for item in hypotheses]
    vocab = sorted({token for doc in docs for token in doc})
    df = Counter(token for token in vocab for doc in docs if token in doc)
    n_docs = max(1, len(docs))
    embeddings: dict[str, dict[str, float]] = {}
    for hypothesis, doc in zip(hypotheses, docs):
        counts = Counter(doc)
        length = max(1, len(doc))
        vector = {}
        for token in vocab:
            tf = counts[token] / length
            idf = math.log((1 + n_docs) / (1 + df[token])) + 1
            value = tf * idf
            if value:
                vector[token] = value
        embeddings[hypothesis.hypothesis_id] = vector
    return vocab, embeddings


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(key, 0.0) * b.get(key, 0.0) for key in keys)
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _representative(hypotheses: list[HypothesisRecord]) -> HypothesisRecord:
    return sorted(
        hypotheses,
        key=lambda item: (
            item.pre_analysis_score or 0.0,
            len(item.falsification_criteria),
            len(item.used_data_features),
        ),
        reverse=True,
    )[0]


def cluster_hypotheses(hypotheses: list[HypothesisRecord], config: dict[str, Any]) -> tuple[list[ProximityCluster], list[dict[str, Any]]]:
    threshold = float(config.get("proximity", {}).get("distance_threshold", 0.35))
    max_cluster = int(config.get("proximity", {}).get("max_cluster_size", 8))
    vocab, embeddings = tfidf_embeddings(hypotheses)
    clusters: list[list[HypothesisRecord]] = []
    for hypothesis in hypotheses:
        placed = False
        for cluster in clusters:
            rep = _representative(cluster)
            similarity = cosine(embeddings[hypothesis.hypothesis_id], embeddings[rep.hypothesis_id])
            if similarity >= 1.0 - threshold and len(cluster) < max_cluster:
                cluster.append(hypothesis)
                placed = True
                break
        if not placed:
            clusters.append([hypothesis])
    output_clusters = []
    for index, cluster in enumerate(clusters, start=1):
        rep = _representative(cluster)
        sims = [cosine(embeddings[rep.hypothesis_id], embeddings[item.hypothesis_id]) for item in cluster if item.hypothesis_id != rep.hypothesis_id]
        output_clusters.append(
            ProximityCluster(
                cluster_id=f"C{index:03d}",
                hypothesis_ids=[item.hypothesis_id for item in cluster],
                representative_id=rep.hypothesis_id,
                cluster_label=rep.mechanism,
                diversity_score=round(1.0 - (sum(sims) / len(sims) if sims else 0.0), 4),
                similarity_summary=f"{len(cluster)} hypotheses around {rep.mechanism}",
            )
        )
    embedding_rows = []
    for hypothesis in hypotheses:
        vector = embeddings[hypothesis.hypothesis_id]
        embedding_rows.append({"hypothesis_id": hypothesis.hypothesis_id, **{token: round(vector.get(token, 0.0), 6) for token in vocab[:50]}})
    return output_clusters, embedding_rows


def run_proximity_agent(hypotheses: list[HypothesisRecord], config: dict[str, Any]) -> dict[str, Any]:
    root = Path(config["_project_root"])
    outputs = config.get("outputs", {})
    clusters, embedding_rows = cluster_hypotheses(hypotheses, config)
    write_csv(resolve_path(outputs["hypothesis_embeddings"], root), embedding_rows)
    write_json(resolve_path(outputs["proximity_clusters"], root), [item.model_dump(mode="json") for item in clusters])
    representative_ids = {cluster.representative_id for cluster in clusters}
    return {"clusters": clusters, "embedding_rows": embedding_rows, "representative_ids": representative_ids}
