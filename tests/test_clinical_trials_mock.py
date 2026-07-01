from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.knowledge_sources.clinical_trials import fetch_clinical_trials


class MockResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {"nctId": "NCT00000001", "briefTitle": "CBT-I for insomnia"},
                        "conditionsModule": {"conditions": ["Insomnia"]},
                        "designModule": {"studyType": "Interventional", "enrollmentInfo": {"count": 20, "type": "Actual"}},
                        "armsInterventionsModule": {"interventions": [{"name": "CBT-I", "type": "Behavioral"}]},
                        "statusModule": {"overallStatus": "COMPLETED"},
                        "outcomesModule": {"primaryOutcomes": [{"measure": "ISI"}]},
                        "eligibilityModule": {"minimumAge": "18 Years", "sex": "ALL"},
                        "contactsLocationsModule": {"locations": []},
                        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Mock Sponsor"}},
                    }
                }
            ]
        }


class MockSession:
    def get(self, *args, **kwargs):
        return MockResponse()


def test_clinical_trials_mock_no_real_api(monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_ENABLE_CLINICALTRIALS_LIVE", "true")
    config = load_config("configs/knowledge_sources_config.yaml")
    records, warnings = fetch_clinical_trials(config, session=MockSession())
    assert records
    assert records[0]["nct_id"] == "NCT00000001"
    assert records[0]["intervention_types_json"] == ["Behavioral"]

