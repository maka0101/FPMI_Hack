"""Local Gemma encoder for microsoft/harrier-oss-v1-270m."""
import os

import torch
from transformers import AutoModel, AutoTokenizer


def device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class Harrier:
    def __init__(self, weights, max_length):
        self.device = device()
        self.max_length = max_length
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.tokenizer = AutoTokenizer.from_pretrained(weights, local_files_only=True, padding_side="right")
        dtype = torch.float32 if self.device == "cpu" else torch.bfloat16
        self.model = AutoModel.from_pretrained(
            weights, local_files_only=True, use_safetensors=True, dtype=dtype, attn_implementation="sdpa"
        ).eval().to(self.device)

    @torch.inference_mode()
    def encode(self, texts, *, normalize):
        inputs = self.tokenizer(texts, padding=True, pad_to_multiple_of=16, truncation=True,
                                max_length=self.max_length, return_tensors="pt").to(self.device)
        hidden = self.model(**inputs).last_hidden_state
        last = inputs["attention_mask"].sum(dim=1) - 1
        vectors = hidden[torch.arange(len(texts), device=self.device), last].float()
        if normalize:
            vectors = torch.nn.functional.normalize(vectors, dim=1)
        return vectors.cpu().numpy()
