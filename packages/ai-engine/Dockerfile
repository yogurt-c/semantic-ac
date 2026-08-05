FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# llama-cpp-python은 플랫폼에 따라 prebuilt wheel이 없으면 소스에서 빌드된다
# (예: Apple Silicon 호스트에서 linux/arm64로 빌드하는 경우). --extra models
# 설치가 실패하지 않도록 빌드 도구를 미리 설치해둔다.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

# pyproject.toml/uv.lock이 바뀌지 않는 한 이 레이어(sentence-transformers/
# llama-cpp-python 포함)는 Docker 빌드 캐시로 재사용된다 — 코드만 바뀐 재빌드는
# 무거운 의존성을 다시 설치하지 않는다.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project --no-dev --extra models

COPY src ./src
RUN uv sync --locked --no-dev --extra models

ENV PATH="/app/.venv/bin:$PATH"

# 기본값은 EMBEDDING_PROVIDER=hashing / KEYWORD_GENERATOR_PROVIDER=noop로
# stub_components의 placeholder를 사용한다. 실모델(E5/Qwen) 연결 방법은
# README.md "환경 변수"/"로드맵" 섹션 참고.
CMD ["python", "-m", "ai_engine.runner"]
