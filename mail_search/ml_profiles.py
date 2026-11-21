"""Versioned encoder profiles and CPU inference adapters."""

import hashlib
import json
import os
import re
import zlib
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


Identifier = Annotated[str, StringConstraints(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')]
Digest = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]
WORDS = re.compile(r'[^\W_]+')


def stable_hash(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Profile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    profile_id: Identifier
    adapter: Literal['word-hash', 'subword-hash', 'sentence-transformers']
    model_id: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    tokenizer_id: str = Field(min_length=1)
    tokenizer_revision: str = Field(min_length=1)
    parameter_count: int = Field(ge=0)
    dimensions: int = Field(ge=1)
    max_length: int = Field(ge=1)
    document_template: str
    query_prefix: str
    normalize: bool
    weights_dir: str | None = None
    files_sha256: dict[str, Digest] = Field(default_factory=dict)

    @model_validator(mode='after')
    def check_artifacts(self):
        if self.document_template.count('{doc}') != 1:
            raise ValueError('document_template must contain {doc} once')
        if self.adapter == 'sentence-transformers':
            if not self.weights_dir or not self.files_sha256:
                raise ValueError('weights_dir and files_sha256 are required')
            for revision in (self.model_revision, self.tokenizer_revision):
                if not re.fullmatch(r'[0-9a-f]{40}', revision):
                    raise ValueError('use a pinned 40-character revision')
            for relative in (self.weights_dir, *self.files_sha256):
                if Path(relative).is_absolute() or '..' in Path(relative).parts:
                    raise ValueError('model paths must be relative to their configured root')
        return self

    def document_settings(self) -> dict:
        return self.model_dump(exclude={'profile_id', 'query_prefix', 'weights_dir', 'parameter_count'})


def read_profile(profile_id: str) -> Profile:
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', profile_id):
        raise ValueError('invalid profile ID')
    path = Path(os.getenv('PROFILE_DIR', 'models/profiles')) / f'{profile_id}.yaml'
    profile = Profile.model_validate(yaml.safe_load(path.read_text(encoding='utf-8')))
    if profile.profile_id != profile_id:
        raise ValueError('profile_id does not match the filename')
    return profile


@lru_cache(maxsize=100_000)
def feature_hash(feature: str) -> int:
    return zlib.crc32(feature.encode('utf-8'))


class Encoder:
    def __init__(self, profile: Profile, artifact_dir: Path):
        self.profile = profile
        self.model = None
        if profile.adapter == 'sentence-transformers':
            weights = artifact_dir / profile.weights_dir
            for name, expected in profile.files_sha256.items():
                if file_hash(weights / name) != expected:
                    raise ValueError(f'weight/tokenizer checksum mismatch for {name}')
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(str(weights.resolve()), device='cpu', local_files_only=True,
                                             trust_remote_code=False)
            self.model.max_seq_length = profile.max_length
            if self.model.get_sentence_embedding_dimension() != profile.dimensions:
                raise ValueError('model output dimension differs from profile')

    def encode(self, texts: list[str]) -> np.ndarray:
        profile = self.profile
        if self.model is not None:
            vectors = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=profile.normalize,
                                        batch_size=16, show_progress_bar=False)
            return np.asarray(vectors, dtype=np.float32)
        vectors = np.zeros((len(texts), profile.dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            features = WORDS.findall(text.casefold().replace('ё', 'е'))[:profile.max_length]
            if profile.adapter == 'subword-hash':
                # A second representation combines whole words and shared three-letter fragments.
                trigrams = [word[i:i+3] for word in features for i in range(len(word)-2)]
                features = features + ['#' + trigram for trigram in trigrams]
            codes = np.fromiter((feature_hash(word) for word in features), dtype=np.uint32)
            if len(codes):
                weights = np.where(codes >> 31, -1.0, 1.0)
                vectors[row] = np.bincount(codes % profile.dimensions, weights=weights,
                                           minlength=profile.dimensions)
        if profile.normalize:
            lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
            np.divide(vectors, lengths, out=vectors, where=lengths != 0)
        return vectors
