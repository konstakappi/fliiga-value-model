from fliiga_model.collector import FliigaCollector


def test_collector_normalizes_and_filters_mens_matches():
    posts = [
        {
            "id": 1,
            "link": "https://example.test/match/1",
            "title": {"rendered": "Classic vs Oilers"},
            "meta": {
                "_sarja": "Miehet",
                "_torneopal_id": "123",
                "_ottelu_aika": "2025-01-02 18:30:00",
                "_kausi": "2024-2025",
                "_kotimaalit": 7,
                "_vierasmaalit": 5,
            },
        },
        {
            "id": 2,
            "link": "https://example.test/match/2",
            "title": {"rendered": "TPS vs PSS"},
            "meta": {"_sarja": "Naiset", "_ottelu_aika": "2025-01-03 18:30:00"},
        },
    ]
    result = FliigaCollector.normalize(posts)
    assert len(result.completed) == 1
    assert result.completed.iloc[0].home_team == "Classic"
    assert result.completed.iloc[0].home_goals == 7


def test_collector_skips_past_zero_zero_placeholders():
    posts = [
        {
            "id": 3,
            "link": "https://example.test/match/3",
            "title": {"rendered": "Classic vs Oilers"},
            "meta": {
                "_sarja": "Miehet",
                "_torneopal_id": "456",
                "_ottelu_aika": "2025-01-02 18:30:00",
                "_kausi": "2024-2025",
                "_kotimaalit": 0,
                "_vierasmaalit": 0,
            },
        }
    ]
    result = FliigaCollector.normalize(posts)
    assert result.completed.empty
    assert result.fixtures.empty
