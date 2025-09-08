import json

from langchain_core.prompts import ChatPromptTemplate

from app.advanced_funcs.logging_client import logger
from app.agents.llm_init import llm
from app.server.mcp_server import get_available_tools


async def planner_agent(state: dict) -> dict:
    """Агент-планировщик. Динамически получает список инструментов и строит план."""

    # Получаем актуальный список инструментов
    tools = await get_available_tools()

    # Формируем описание инструментов для LLM
    tools_description = "\n".join(
        [
            f"- {tool['name']}: {tool['description']} (аргументы: {list(tool['input_schema'].get('properties', {}).keys()) if tool['input_schema'] else 'нет'})"
            for tool in tools
        ]
    )

    planner_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                f"""
            Ты — строгий планировщик. Твоя задача — РАЗЛОЖИТЬ запрос на последовательность шагов с указанием ТОЧНОГО порядка вызова инструментов.

            Доступные инструменты:
            {tools_description}

            Отвечай ТОЛЬКО в формате JSON:
            {{
            "plan": "описание плана",
            "tool_sequence": ["tool_name1", "tool_name2", ...]
            }}

            НЕ ОТКЛОНЯЙСЯ ОТ ЭТОГО ФОРМАТА. НЕ ДОБАВЛЯЙ ЛИШНЕГО.
        """,
            ),
            ("human", "{input}"),
        ]
    )

    chain = planner_prompt | llm
    response = await chain.ainvoke({"input": state["user_input"]})

    try:
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        parsed = json.loads(content)
        plan = parsed["plan"]
        tool_sequence = parsed["tool_sequence"]

        # Проверяем, что все инструменты существуют
        available_tool_names = {tool["name"] for tool in tools}
        invalid_tools = [t for t in tool_sequence if t not in available_tool_names]
        if invalid_tools:
            logger.warning(
                f"Недопустимые инструменты в плане: {invalid_tools}. Заменяю на первый доступный."
            )
            tool_sequence = (
                [tool_sequence[0]] if tool_sequence else ["get_current_time"]
            )

    except Exception as e:
        logger.error(f"Ошибка парсинга плана: {e}. Использую резервный план.")
        plan = "Выполнить запрос через доступные инструменты."
        tool_sequence = [tools[0]["name"]] if tools else []

    logger.info(f"Сгенерирован план: {plan}")
    logger.info(f"Последовательность инструментов: {tool_sequence}")

    return {
        **state,
        "plan": plan,
        "tool_sequence": tool_sequence,
        "current_step": "executing_tools",
        "available_tools": tools,
    }
