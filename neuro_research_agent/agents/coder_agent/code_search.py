from __future__ import annotations

from typing import Any

import requests


def github_code_search(query: str, max_results: int = 5, timeout: int = 10) -> list[dict[str, Any]]:
    url = "https://api.github.com/search/repositories"
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": max_results}
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    results = []
    for item in response.json().get("items", []):
        results.append(
            {
                "name": item.get("full_name", ""),
                "url": item.get("html_url", ""),
                "description": item.get("description", ""),
                "stars": item.get("stargazers_count", 0),
                "language": item.get("language", ""),
                "source": "github",
            }
        )
    return results


def fallback_code_resources(paradigm_id: str) -> list[dict[str, Any]]:
    resources = {
        "resting_state_functional_connectivity": [
            {"name": "nilearn connectivity examples", "url": "https://nilearn.github.io/stable/connectivity/index.html", "description": "Nilearn examples for connectome and correlation matrices.", "source": "curated"}
        ],
        "task_glm": [
            {"name": "nilearn GLM examples", "url": "https://nilearn.github.io/stable/glm/index.html", "description": "First-level and second-level fMRI GLM examples.", "source": "curated"}
        ],
        "alff_falff_frequency": [
            {"name": "nilearn signal cleaning", "url": "https://nilearn.github.io/", "description": "Use nibabel/scipy/nilearn signal utilities for frequency-domain metrics.", "source": "curated"}
        ],
        "mvpa_decoding": [
            {"name": "nilearn decoding examples", "url": "https://nilearn.github.io/stable/decoding/index.html", "description": "Searchlight and decoding workflows.", "source": "curated"}
        ],
        "eeg_meg_time_frequency": [
            {"name": "MNE-Python time-frequency examples", "url": "https://mne.tools/stable/auto_tutorials/time-freq/index.html", "description": "Spectral and time-frequency analysis for EEG/MEG.", "source": "curated"}
        ],
        "erp_evoked_response": [
            {"name": "MNE-Python evoked tutorials", "url": "https://mne.tools/stable/auto_tutorials/evoked/index.html", "description": "ERP/evoked averaging and condition contrasts.", "source": "curated"}
        ],
        "source_connectivity": [
            {"name": "MNE connectivity examples", "url": "https://mne.tools/mne-connectivity/stable/", "description": "Connectivity estimation for sensor and source data.", "source": "curated"}
        ],
        "spike_train_statistics": [
            {"name": "SpikeInterface", "url": "https://spikeinterface.readthedocs.io/", "description": "Spike sorting, unit curation, and spike-train analysis.", "source": "curated"},
            {"name": "Elephant", "url": "https://elephant.readthedocs.io/", "description": "Electrophysiology statistics and spike-train analysis.", "source": "curated"}
        ],
        "lfp_spectral_coupling": [
            {"name": "NeuroDSP", "url": "https://neurodsp-tools.github.io/neurodsp/", "description": "Spectral analysis for neural time series.", "source": "curated"}
        ],
        "behavioral_computational_modeling": [
            {"name": "HDDM", "url": "https://hddm.readthedocs.io/", "description": "Hierarchical drift diffusion modeling for behavior.", "source": "curated"}
        ],
        "eye_tracking_pupil_gaze": [
            {"name": "PyGaze", "url": "https://www.pygaze.org/", "description": "Eye-tracking experiment and analysis utilities.", "source": "curated"}
        ],
        "calcium_population_dynamics": [
            {"name": "Suite2p", "url": "https://suite2p.readthedocs.io/", "description": "Calcium imaging processing and ROI extraction.", "source": "curated"},
            {"name": "CaImAn", "url": "https://caiman.readthedocs.io/", "description": "Calcium imaging analysis pipeline.", "source": "curated"}
        ],
        "neurogenomics_association": [
            {"name": "Scanpy", "url": "https://scanpy.readthedocs.io/", "description": "Single-cell and transcriptomics analysis.", "source": "curated"}
        ],
        "multimodal_neuroscience_fusion": [
            {"name": "PyNWB", "url": "https://pynwb.readthedocs.io/", "description": "Neurodata Without Borders data access for multimodal neuroscience.", "source": "curated"}
        ],
    }
    return resources.get(paradigm_id, [{"name": "NWB/PyNWB", "url": "https://pynwb.readthedocs.io/", "description": "General neuroscience data access and reproducible analysis examples.", "source": "curated"}])


def search_code_for_paradigm(paradigm_id: str, prompt: str, max_results: int = 10, allow_network: bool = True) -> list[dict[str, Any]]:
    if allow_network:
        query = f"{paradigm_id} neuroscience Python"
        try:
            results = github_code_search(query, max_results=max_results)
            if results:
                return results
        except Exception:
            pass
    return fallback_code_resources(paradigm_id)
