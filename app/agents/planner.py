import json

from langchain_core.prompts import ChatPromptTemplate

from app.agents.llm_init import llm
from app.mcp_server.server import get_available_tools
from app.utility.logging_client import logger


async def planner_agent(state: dict) -> dict:
    """Агент-планировщик. Динамически получает список инструментов и строит план."""

    tools = await get_available_tools()

    tools_description = "\n".join(
        [
            f"- {tool['name']}: {tool['description']} (аргументы: {list(tool['input_schema'].get('properties', {}).keys()) if tool['input_schema'] else 'нет'})"
            for tool in tools
        ]
    )

    json_example = '{{"plan": "описание плана", "tool_sequence": ["tool_name1", "tool_name2", ...]}}'

    system_content = f"""Ты — строгий планировщик. Твоя задача — РАЗЛОЖИТЬ запрос на последовательность шагов с указанием ТОЧНОГО порядка вызова инструментов.

Доступные инструменты:
{tools_description}

Отвечай ТОЛЬКО в формате JSON:
{json_example}

НЕ ОТКЛОНЯЙСЯ ОТ ЭТОГО ФОРМАТА. НЕ ДОБАВЛЯЙ ЛИШНЕГО."""

    messages = [
        ("system", system_content),
        ("human", "{input}"),
    ]

    planner_prompt = ChatPromptTemplate.from_messages(messages)
    planner_prompt = planner_prompt.partial()

    chain = planner_prompt | llm
    response = await chain.ainvoke({"input": state["user_input"]})

    try:
        content = response.content.strip() if hasattr(response, 'content') else str(response).strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        parsed = json.loads(content)
        plan = parsed["plan"]
        tool_sequence = parsed["tool_sequence"]

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
