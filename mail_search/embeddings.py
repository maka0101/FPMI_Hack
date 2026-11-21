from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
import sys

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


DIMENSION = 384
MAX_TOKENS = 512
BATCH_SIZE = 32


class E5Encoder:
    def __init__(self, model_dir):
        model = model_dir / "model_quantized.onnx"
        if not model.is_file():
            model = model_dir / "model.onnx"
        tokenizer = model_dir / "tokenizer.json"
        self.files = (model, tokenizer)
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS)
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, os.cpu_count() or 1)
        self.session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        self.input_names = {item.name for item in self.session.get_inputs()}

    def index(self, passages, cache_path):
        cache_key = self.cache_key(passages) if cache_path else None
        if cache_path and cache_path.is_file():
            with np.load(cache_path, allow_pickle=False) as data:
                if str(data["key"]) == cache_key:
                    vectors = data["vectors"]
                    if vectors.shape == (len(passages), DIMENSION) and vectors.dtype == np.float32:
                        return vectors

        print(f"Индекс multilingual-e5-small: {len(passages)} писем", file=sys.stderr, flush=True)
        vectors = np.empty((len(passages), DIMENSION), dtype=np.float32)
        # Similar text lengths in one batch reduce padding. Rows keep their original order.
        order = sorted(range(len(passages)), key=lambda i: len(passages[i]))
        for start in range(0, len(order), BATCH_SIZE):
            rows = order[start:start + BATCH_SIZE]
            vectors[rows] = self.encode([f"passage: {passages[i]}" for i in rows])
            if start // BATCH_SIZE % 32 == 31:
                print(f"Закодировано {start + len(rows)} из {len(order)} писем", file=sys.stderr, flush=True)

        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=cache_path.parent, delete=False) as stream:
                temp_path = Path(stream.name)
                try:
                    np.savez(stream, key=cache_key, vectors=vectors)
                    stream.close()
                    os.replace(temp_path, cache_path)
                finally:
                    temp_path.unlink(missing_ok=True)
        return vectors

    def cache_key(self, passages):
        digest = sha256(f"multilingual-e5-small:{MAX_TOKENS}:mean-pooling-l2:v1".encode())
        for path in self.files:
            digest.update(path.name.encode())
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        for text in passages:
            encoded = text.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
        return digest.hexdigest()

    def encode(self, texts):
        batch = self.tokenizer.encode_batch(texts)
        width = max(len(item.ids) for item in batch)
        pad_id = self.tokenizer.token_to_id("<pad>")
        for item in batch:
            item.pad(width, pad_id=pad_id, pad_token="<pad>")
        mask = np.array([item.attention_mask for item in batch], dtype=np.int64)
        inputs = {
            "input_ids": np.array([item.ids for item in batch], dtype=np.int64),
            "attention_mask": mask,
        }
        if "token_type_ids" in self.input_names:
            inputs["token_type_ids"] = np.array([item.type_ids for item in batch], dtype=np.int64)
        hidden = self.session.run(["last_hidden_state"], inputs)[0]
        vectors = np.einsum("btd,bt->bd", hidden, mask.astype(np.float32))
        vectors /= mask.sum(axis=1, dtype=np.float32)[:, None]
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors

    def top_ids(self, embeddings, eligible_ids, query, limit):
        query_vector = self.encode([f"query: {query}"])[0]
        rows = np.asarray(eligible_ids) - 1  # SQLite row IDs start at 1.
        scores = np.einsum("ij,j->i", embeddings[rows], query_vector)
        order = np.argsort(-scores, kind="stable")[:limit]
        return [eligible_ids[position] for position in order]
