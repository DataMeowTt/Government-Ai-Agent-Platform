import json
import os
import urllib.error
import urllib.request


AI_AGENT_URL = os.getenv("AI_AGENT_URL", "http://localhost:8000/agent/chat")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev-internal-key")

MESSAGES = (
    "So sánh trade openness của Việt Nam và Malaysia từ 2010 đến 2022",
    "So sánh GDP per capita của Brazil và Mexico từ 2000 đến 2022",
    "So sánh current account/GDP của Việt Nam và Philippines từ 2010 đến 2022",
    "Coverage dữ liệu nợ công/GDP của Việt Nam",
    "Coverage dữ liệu thất nghiệp của các nước ASEAN",
)


def post_message(message: str) -> dict:
    body = json.dumps({"message": message}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        AI_AGENT_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-internal-api-key": INTERNAL_API_KEY,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    for message in MESSAGES:
        print(f"\n> {message}")
        try:
            data = post_message(message)
        except urllib.error.URLError as error:
            print(f"REQUEST_FAILED: {error}")
            continue
        print(
            json.dumps(
                {
                    "status": data.get("status"),
                    "questionType": data.get("questionType"),
                    "pipeline": (data.get("metadata") or {}).get("pipeline"),
                    "routerDebug": data.get("routerDebug"),
                    "warnings": data.get("warnings"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
