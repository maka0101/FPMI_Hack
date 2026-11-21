"""CPU inference for a local multilingual E5 ONNX export."""

import os

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


class OnnxE5:
    def __init__(self, weights, max_length):
        self.tokenizer = Tokenizer.from_file(str(weights / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=max_length)
        self.pad_id = self.tokenizer.token_to_id("<pad>")
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, os.cpu_count() or 1)
        self.session = ort.InferenceSession(
            str(weights / "model_quantized.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.input_names = {item.name for item in self.session.get_inputs()}

    def encode(self, texts, *, normalize):
        batch = self.tokenizer.encode_batch(texts)
        width = max(len(item.ids) for item in batch)
        for item in batch:
            item.pad(width, pad_id=self.pad_id, pad_token="<pad>")
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
        if normalize:
            vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors
