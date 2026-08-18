from __future__ import annotations

import numpy as np

from sleep_ai_scientist.feature_extraction.extractors.fmri_feature_extractor import _network_centroids


def test_network_centroids_are_computed_from_atlas_labels_and_affine() -> None:
    atlas = np.zeros((4, 4, 4), dtype=np.int32)
    atlas[1, 1, 1] = 10
    atlas[3, 1, 1] = 49
    atlas[2, 2, 2] = 1008
    affine = np.array(
        [
            [2.0, 0.0, 0.0, 10.0],
            [0.0, 3.0, 0.0, 20.0],
            [0.0, 0.0, 4.0, 30.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )

    coords = _network_centroids(atlas, affine, {"thalamus": [10, 49], "DMN": [1008]})

    assert coords["thalamus"] == (14.0, 23.0, 34.0)
    assert coords["DMN"] == (14.0, 26.0, 38.0)
