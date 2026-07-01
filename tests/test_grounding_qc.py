from sleep_ai_scientist.grounding.grounding_qc import run_grounding_qc
from sleep_ai_scientist.schemas.data_profile import DataProfile, FeatureProfile, MappingStatus, VariableMappingRecord


def test_grounding_qc_detects_hallucinated_variable():
    analysis_ready = DataProfile(
        profile_type="analysis_ready_profile",
        features=[FeatureProfile(feature_name="real_feature", modality="EEG", source_file="x", source_column="real_feature")],
    )
    mappings = [
        VariableMappingRecord(
            concept="slow-wave generation",
            candidate_variables=["fake_feature"],
            approved_data_features=["fake_feature"],
            modality="EEG",
            mapping_status=MappingStatus.mapped,
        )
    ]

    report = run_grounding_qc([], [], mappings, analysis_ready, ["slow-wave generation"])

    assert report["checks"]["check_no_hallucinated_variables"]["passed"] is False
    assert report["checks"]["check_no_hallucinated_variables"]["hallucinated_variables"] == ["fake_feature"]
