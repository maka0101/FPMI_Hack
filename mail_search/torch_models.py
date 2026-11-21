import json
import os

import numpy as np
import torch
from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer
from transformers import __version__ as transformers_version

from .embeddings import DenseEncoder, MAX_TOKENS
from .model_catalog import EMBEDDERS, RERANKERS


PROMPT_NAMES = {
    "granite97": ("query", "document"),
    "user2-small": ("search_query", "search_document"),
    "harrier270": ("web_search_query", None),
}


def resolve_device(device):
    if device == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if (device == "mps" and not torch.backends.mps.is_available()) or (
        device == "cuda" and not torch.cuda.is_available()
    ):
        raise ValueError(f"Устройство {device} недоступно")
    return device


def load_model(model_dir, device, model_class):
    dtype = torch.float32 if device == "cpu" else torch.bfloat16
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    # These checkpoints use ModernBERT, XLM-R or Gemma tokenizers. Transformers 4.57
    # can misidentify a local Gemma tokenizer as a Mistral tokenizer.
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, fix_mistral_regex=False)
    tokenizer.padding_side = "right"
    model = model_class.from_pretrained(
        model_dir, dtype=dtype, attn_implementation="sdpa", local_files_only=True,
        use_safetensors=True,
    ).eval().to(device)
    return tokenizer, model, str(dtype).removeprefix("torch.")


class TorchEncoder(DenseEncoder):
    def __init__(self, name, model_dir, device):
        self.name = EMBEDDERS[name]
        self.device = resolve_device(device)
        self.tokenizer, self.model, self.precision = load_model(model_dir, self.device, AutoModel)
        pooling = json.loads((model_dir / "1_Pooling/config.json").read_text(encoding="utf-8"))
        self.dimension = pooling["word_embedding_dimension"]
        modes = [mode for mode in ("cls_token", "lasttoken", "mean_tokens") if pooling[f"pooling_mode_{mode}"]]
        if len(modes) != 1:
            raise ValueError(f"Неизвестный pooling в {model_dir}")
        self.pooling = modes[0]
        config = json.loads((model_dir / "config_sentence_transformers.json").read_text(encoding="utf-8"))
        query_name, passage_name = PROMPT_NAMES[name]
        self.query_prefix = config["prompts"][query_name]
        self.passage_prefix = config["prompts"][passage_name] if passage_name else ""
        self.files = tuple(
            model_dir / file for file in (
                "model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json",
                "1_Pooling/config.json", "config_sentence_transformers.json",
            )
        )
        self.cache_version = (
            f"{self.name}:{MAX_TOKENS}:{self.pooling}:{self.device}:{self.precision}:"
            f"torch-{torch.__version__}:transformers-{transformers_version}:v1"
        )

    @torch.inference_mode()
    def encode(self, texts):
        inputs = self.tokenizer(
            texts, padding=True, pad_to_multiple_of=16, truncation=True, max_length=MAX_TOKENS,
            return_tensors="pt",
        ).to(self.device)
        hidden = self.model(**inputs).last_hidden_state
        mask = inputs["attention_mask"]
        if self.pooling == "cls_token":
            vectors = hidden[:, 0].float()
        elif self.pooling == "lasttoken":
            rows = torch.arange(len(texts), device=self.device)
            vectors = hidden[rows, mask.sum(dim=1) - 1].float()
        else:
            vectors = (hidden.float() * mask.unsqueeze(-1)).sum(dim=1) / mask.sum(dim=1, keepdim=True)
        vectors = torch.nn.functional.normalize(vectors, dim=1).cpu().numpy()
        if not np.isfinite(vectors).all():
            raise RuntimeError(f"{self.name} вернул неконечный эмбеддинг")
        return vectors


class CrossEncoder:
    def __init__(self, name, model_dir, device):
        self.name = RERANKERS[name]
        self.device = resolve_device(device)
        self.tokenizer, self.model, self.precision = load_model(
            model_dir, self.device, AutoModelForSequenceClassification,
        )

    @torch.inference_mode()
    def rank(self, query, passages):
        inputs = self.tokenizer(
            [query] * len(passages), passages, padding=True, pad_to_multiple_of=16,
            truncation=True, max_length=MAX_TOKENS, return_tensors="pt",
        ).to(self.device)
        scores = self.model(**inputs).logits[:, 0].float().cpu().numpy()
        if not np.isfinite(scores).all():
            raise RuntimeError(f"{self.name} вернул неконечные оценки")
        return np.argsort(-scores, kind="stable").tolist()
