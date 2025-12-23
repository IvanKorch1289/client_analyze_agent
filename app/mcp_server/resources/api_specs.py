"""
API specifications and field reference.

Provides OpenAPI/Swagger specs for external APIs.
"""

from typing import Any, Dict, List, Optional

from app.mcp_server.resources.reference_data import API_SOURCES
from app.shared.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# API SPECIFICATIONS
# ============================================================================


def get_api_spec(api_name: str) -> Dict[str, Any]:
    """
    Get API specification for external service.

    Args:
        api_name: API name (dadata, casebook, infosfera, perplexity, tavily)

    Returns:
        API specification dict

    Raises:
        KeyError: If API not found

    Examples:
        >>> spec = get_api_spec("dadata")
        >>> spec["name"]
        "DaData"
    """
    api_name_lower = api_name.lower()

    if api_name_lower not in API_SOURCES:
        raise KeyError(f"Unknown API: {api_name}")

    return API_SOURCES[api_name_lower]


def get_field_reference(api_name: str) -> List[str]:
    """
    Get list of important fields for an API.

    Args:
        api_name: API name

    Returns:
        List of field paths

    Examples:
        >>> fields = get_field_reference("dadata")
        >>> "inn" in fields
        True
    """
    spec = get_api_spec(api_name)
    return spec.get("fields", [])


# ============================================================================
# SWAGGER SPECS (Simplified)
# ============================================================================


DADATA_SWAGGER = {
    "openapi": "3.0.0",
    "info": {
        "title": "DaData API",
        "version": "4.1",
        "description": "API для получения данных из ЕГРЮЛ",
        "contact": {
            "url": "https://dadata.ru/api/",
        },
    },
    "servers": [
        {
            "url": "https://suggestions.dadata.ru/suggestions/api/4_1/rs",
        }
    ],
    "paths": {
        "/suggest/party": {
            "post": {
                "summary": "Подсказки по организациям",
                "description": "Поиск организаций по названию или ИНН",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Название или ИНН компании",
                                    },
                                    "count": {
                                        "type": "integer",
                                        "default": 10,
                                        "description": "Максимальное количество результатов",
                                    },
                                },
                                "required": ["query"],
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Успешный ответ",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "suggestions": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "value": {"type": "string"},
                                                    "data": {
                                                        "type": "object",
                                                        "properties": {
                                                            "inn": {"type": "string"},
                                                            "kpp": {"type": "string"},
                                                            "ogrn": {"type": "string"},
                                                            "name": {
                                                                "type": "object",
                                                                "properties": {
                                                                    "full_with_opf": {
                                                                        "type": "string"
                                                                    }
                                                                },
                                                            },
                                                            "state": {
                                                                "type": "object",
                                                                "properties": {
                                                                    "status": {
                                                                        "type": "string"
                                                                    },
                                                                    "registration_date": {
                                                                        "type": "integer"
                                                                    },
                                                                },
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                        }
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    },
}


CASEBOOK_SWAGGER = {
    "openapi": "3.0.0",
    "info": {
        "title": "Casebook API",
        "version": "3.0",
        "description": "API для получения данных об арбитражных делах",
        "contact": {
            "url": "https://api3.casebook.ru/api-docs/",
        },
    },
    "servers": [
        {
            "url": "https://api3.casebook.ru/api",
        }
    ],
    "paths": {
        "/search": {
            "get": {
                "summary": "Поиск по ИНН",
                "description": "Получить информацию о судебных делах компании",
                "parameters": [
                    {
                        "name": "inn",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "ИНН компании",
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Успешный ответ",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "cases": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "case_number": {"type": "string"},
                                                    "decision": {"type": "string"},
                                                    "amount": {"type": "number"},
                                                },
                                            },
                                        },
                                        "bankruptcy": {
                                            "type": "object",
                                            "properties": {
                                                "stage": {"type": "string"},
                                                "manager": {"type": "string"},
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    },
}


def get_swagger_spec(api_name: str) -> Optional[Dict[str, Any]]:
    """
    Get OpenAPI/Swagger spec for an API.

    Args:
        api_name: API name

    Returns:
        Swagger spec dict or None

    Examples:
        >>> spec = get_swagger_spec("dadata")
        >>> spec["openapi"]
        "3.0.0"
    """
    specs = {
        "dadata": DADATA_SWAGGER,
        "casebook": CASEBOOK_SWAGGER,
    }

    return specs.get(api_name.lower())


__all__ = [
    "get_api_spec",
    "get_field_reference",
    "get_swagger_spec",
    "DADATA_SWAGGER",
    "CASEBOOK_SWAGGER",
]

