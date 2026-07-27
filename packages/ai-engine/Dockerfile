FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project --no-dev

COPY src ./src
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# 실모델(E5/Qwen) 연결 전까지는 stub_components의 HashingEmbeddingModel/
# NoopKeywordGenerator로 배치 파이프라인 구조만 검증한다 (README.md "다음 단계" 참고).
CMD ["python", "-m", "ai_engine.runner"]
