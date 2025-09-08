import json

from langchain_core.prompts import ChatPromptTemplate

from app.agents.llm_init import llm


def analyzer_agent(state: dict) -> dict:
    """Агент-аналитик. Принимает результаты инструментов и возвращает структурированный анализ."""
    analyzer_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
Ты — аналитик. На основе результатов инструментов дай структурированный вывод.

Формат ответа:
### Анализ:
{текст}

### Вывод:
{чёткий вывод}

### Рекомендации:
{если есть}
""",
            ),
            ("human", "Результаты: {tool_results}"),
        ]
    )
    chain = analyzer_prompt | llm
    tool_results_str = json.dumps(state["tool_results"], ensure_ascii=False, indent=2)
    response = chain.invoke({"tool_results": tool_results_str})
    return {**state, "analysis_result": response.content, "current_step": "saving"}
