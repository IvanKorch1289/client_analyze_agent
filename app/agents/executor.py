from app.advanced_funcs.logging_client import logger
from app.server.mcp_server import execute_tool


async def tool_executor_agent(state: dict) -> dict:
    """Агент-исполнитель. Вызывает инструменты через MCP-клиент строго по плану."""
    results = []

    for tool_name in state["tool_sequence"]:
        logger.info(f"Выполняю инструмент: {tool_name}")

        # Получаем аргументы из state по соглашению
        arguments = get_tool_args(tool_name, state)

        # Выполняем инструмент
        result = await execute_tool(tool_name, arguments)

        results.append({"tool": tool_name, "arguments": arguments, "result": result})

        # Если инструмент вернул данные — сохраняем их в state для следующих шагов
        if result["success"] and result["data"]:
            state[f"result_{tool_name}"] = result["data"]

    logger.info(f"Все инструменты выполнены. Результатов: {len(results)}")

    return {**state, "tool_results": results, "current_step": "analyzing"}


def get_tool_args(tool_name: str, state: dict) -> dict:
    """Универсальная функция получения аргументов. Использует соглашения именования."""

    # Соглашение 1: если в state есть ключ с именем инструмента — используем его
    if tool_name in state:
        if isinstance(state[tool_name], dict):
            return state[tool_name]
        else:
            logger.warning(
                f"Значение state['{tool_name}'] не является словарём. Игнорирую."
            )

    # Соглашение 2: ищем аргументы по шаблону "arg_<tool_name>_<param>"
    args = {}
    prefix = f"arg_{tool_name}_"
    for key, value in state.items():
        if key.startswith(prefix):
            param_name = key[len(prefix) :]
            args[param_name] = value

    if args:
        return args

    # Соглашение 3: fallback — пустой словарь (инструмент должен обработать сам)
    logger.info(f"Не найдены аргументы для {tool_name}. Передаю пустой словарь.")
    return {}
