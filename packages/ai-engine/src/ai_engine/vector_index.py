from __future__ import annotations

import os
import tempfile
from pathlib import Path

import faiss
import numpy as np

from ai_engine.embeddings import EmbeddingModel


def build_index(keywords: list[str], embedding_model: EmbeddingModel) -> faiss.Index:
    """키워드를 passage로 벡터화해 코사인 유사도(정규화 후 내적) 기반 Faiss 인덱스를 만든다.

    인덱싱 대상은 코퍼스/vocabulary이므로 e5 관례상 passage 인코딩 경로를 쓴다.
    """
    if not keywords:
        raise ValueError("keywords must not be empty")

    vectors = np.asarray(embedding_model.encode_passages(keywords), dtype=np.float32)
    faiss.normalize_L2(vectors)

    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    return index


def save_index_atomic(index: faiss.Index, path: Path | str) -> None:
    """배치 실행마다 새 인덱스를 임시 파일에 쓴 뒤 os.replace로 원자적 교체한다.

    os.replace는 동일 파일시스템 내에서 원자적이므로, 서빙 쪽이 읽는 도중에도
    이전 인덱스 파일 또는 새 인덱스 파일 중 하나만 온전히 보이고 다운타임이 없다.
    """
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=target_path.parent, suffix=".tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        faiss.write_index(index, str(tmp_path))
        os.replace(tmp_path, target_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def load_index(path: Path | str) -> faiss.Index:
    return faiss.read_index(str(path))


def nearest_keywords(
    index: faiss.Index,
    vocabulary: list[str],
    embedding_model: EmbeddingModel,
    query: str,
    top_k: int = 5,
) -> list[str]:
    """query와 의미적으로 가까운 vocabulary 내 키워드를 최대 top_k개 반환한다.

    질의 문자열이므로 e5 관례상 query 인코딩 경로를 쓴다 (인덱싱 경로와 구분).
    """
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    query_vector = np.asarray(embedding_model.encode_query(query), dtype=np.float32).reshape(1, -1)
    faiss.normalize_L2(query_vector)

    _, indices = index.search(query_vector, min(top_k, index.ntotal))
    return [vocabulary[i] for i in indices[0] if i != -1]
