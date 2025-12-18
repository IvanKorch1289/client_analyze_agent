import asyncio
import time


def test_data_collector_runs_inn_sources_in_parallel_and_then_web_search(monkeypatch):
    """
    Требование: сначала параллельные запросы по ИНН, затем Perplexity+Tavily.
    """
    from app.agents import data_collector as dc

    # --- Arrange: фиктивные INN-источники (с задержкой)
    inn_calls = {"dadata": 0, "infosphere": 0, "casebook": 0}
    inn_done = {"dadata": False, "infosphere": False, "casebook": False}
    inn_all_done = asyncio.Event()

    async def _inn_source(name: str):
        inn_calls[name] += 1
        await asyncio.sleep(0.10)
        inn_done[name] = True
        if all(inn_done.values()):
            inn_all_done.set()

    async def fake_fetch_from_dadata(_inn: str):
        await _inn_source("dadata")
        return {"status": "success", "data": {"name": {"full_with_opf": "ООО Ромашка"}, "state": {"status": "ACTIVE"}, "address": {"value": "Москва"}}}

    async def fake_fetch_from_infosphere(_inn: str):
        await _inn_source("infosphere")
        return {"status": "success", "data": []}

    async def fake_fetch_from_casebook(_inn: str):
        await _inn_source("casebook")
        return {"status": "success", "data": []}

    monkeypatch.setattr(dc, "fetch_from_dadata", fake_fetch_from_dadata)
    monkeypatch.setattr(dc, "fetch_from_infosphere", fake_fetch_from_infosphere)
    monkeypatch.setattr(dc, "fetch_from_casebook", fake_fetch_from_casebook)

    # --- Arrange: фиктивные web-поиск клиенты, которые проверяют порядок (inn_all_done должен быть установлен)
    perpl_calls = []
    tav_calls = []

    class FakePerplexity:
        def is_configured(self):
            return True

        async def ask_langchain(self, **kwargs):
            assert inn_all_done.is_set(), "Perplexity вызван до завершения INN-фазы"
            perpl_calls.append(kwargs.get("question", ""))
            return {"success": True, "content": "OK", "citations": ["c1"], "integration": "langchain-openai"}

        async def ask(self, **kwargs):
            assert inn_all_done.is_set(), "Perplexity (fallback) вызван до завершения INN-фазы"
            perpl_calls.append(kwargs.get("question", ""))
            return {"success": True, "content": "OK", "citations": ["c1"], "integration": "httpx-direct"}

    class FakeTavily:
        def is_configured(self):
            return True

        async def search(self, **kwargs):
            assert inn_all_done.is_set(), "Tavily вызван до завершения INN-фазы"
            tav_calls.append(kwargs.get("query", ""))
            return {"success": True, "answer": "OK", "results": [{"url": "u1", "content": "c"}]}

    monkeypatch.setattr(dc.PerplexityClient, "get_instance", classmethod(lambda cls: FakePerplexity()))
    monkeypatch.setattr(dc.TavilyClient, "get_instance", classmethod(lambda cls: FakeTavily()))

    state = {
        "client_name": "Тестовая компания",
        "inn": "7707083893",
        "search_intents": [
            {"id": "reputation", "query": "репутация компании Тестовая компания отзывы", "description": "Репутация"},
            {"id": "news", "query": "Тестовая компания новости", "description": "Новости"},
        ],
    }

    # --- Act
    t0 = time.perf_counter()
    result = asyncio.run(dc.data_collector_agent(state))
    elapsed = time.perf_counter() - t0

    # --- Assert: INN-источники отработали (и по времени похоже на параллельность)
    assert inn_calls == {"dadata": 1, "infosphere": 1, "casebook": 1}
    assert elapsed < 0.25, f"INN-фаза выглядит непараллельной, elapsed={elapsed:.3f}s"

    # --- Assert: web-поиск вызван по обоим интентам
    assert len(perpl_calls) == 2
    assert len(tav_calls) == 2

    # --- Assert: search_results содержит оба intent_id
    intent_ids = {r.get("intent_id") for r in result.get("search_results", [])}
    assert "reputation" in intent_ids
    assert "news" in intent_ids


def test_data_collector_falls_back_when_no_intents(monkeypatch):
    from app.agents import data_collector as dc

    class FakePerplexity:
        def is_configured(self):
            return True

        async def ask_langchain(self, **kwargs):
            return {"success": True, "content": "OK", "citations": []}

        async def ask(self, **kwargs):
            return {"success": True, "content": "OK", "citations": []}

    class FakeTavily:
        def is_configured(self):
            return True

        async def search(self, **kwargs):
            return {"success": True, "answer": "OK", "results": []}

    monkeypatch.setattr(dc.PerplexityClient, "get_instance", classmethod(lambda cls: FakePerplexity()))
    monkeypatch.setattr(dc.TavilyClient, "get_instance", classmethod(lambda cls: FakeTavily()))

    state = {"client_name": "Тестовая компания", "inn": "", "search_intents": []}
    result = asyncio.run(dc.data_collector_agent(state))

    intent_ids = {r.get("intent_id") for r in result.get("search_results", [])}
    assert "reputation" in intent_ids

