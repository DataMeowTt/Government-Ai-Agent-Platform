import json
import logging
import socket
from typing import Any
from urllib import error, request

from app.core.config import settings


logger = logging.getLogger(__name__)


def call_parser_service(
    message: str,
    context: dict[str, Any] | None = None,
    debug: bool | None = None,
) -> dict[str, Any] | None:
    base_url = (settings.parser_service_base_url or "").strip().rstrip("/")
    if not base_url:
        logger.warning("Parser service unavailable: PARSER_SERVICE_BASE_URL is not configured")
        return None

    payload = {
        "message": message,
        "context": context,
        "debug": settings.parser_debug if debug is None else debug,
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base_url}/parse",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    timeout_seconds = max(settings.parser_service_timeout_ms, 1) / 1000

    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
            return json.loads(response_body)
    except error.HTTPError as exc:
        logger.warning("Parser service HTTP error: status=%s", exc.code)
    except error.URLError as exc:
        logger.warning("Parser service network error: %s", exc.reason)
    except (TimeoutError, socket.timeout):
        logger.warning("Parser service timeout")
    except json.JSONDecodeError:
        logger.warning("Parser service returned invalid JSON")
    except Exception:
        logger.exception("Unexpected parser service error")

    return None
