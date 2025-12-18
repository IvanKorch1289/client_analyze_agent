import asyncio


def test_report_analyzer_produces_canonical_report_schema():
    from app.agents.report_analyzer import report_analyzer_agent
    from app.schemas.report import ClientAnalysisReport

    state = {
        "client_name": "Тест",
        "inn": "7707083893",
        "source_data": {
            "dadata": {"success": True, "data": {"name": {"full_with_opf": "ООО Тест"}, "state": {"status": "ACTIVE"}, "address": {"value": "Москва"}}},
            "infosphere": {"success": True, "data": []},
            "casebook": {"success": True, "data": []},
        },
        "search_results": [
            {
                "intent_id": "news",
                "description": "Новости",
                "query": "Тест новости",
                "success": True,
                "content": "Негативных новостей нет.",
                "citations": ["https://example.com"],
                "sentiment": {"label": "neutral", "score": 0.0},
            }
        ],
    }

    out = asyncio.run(report_analyzer_agent(state))
    report = out["report"]
    # validate shape
    ClientAnalysisReport.model_validate(report)

