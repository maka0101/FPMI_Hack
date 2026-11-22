import argparse
from pathlib import Path

from huggingface_hub import snapshot_download

from .model_catalog import EMBEDDERS, RERANKERS


REVISIONS = {
    "granite97": "835ad14087e140460703cf0fae09f97d469d65c2",
    "user2-small": "23f65b34cf7632032061f5cc66c14714e6d4cee4",
    "harrier270": "31de22b673913c7d658c0f03f792d77c2dcf8ebd",
    "ru-reranker": "46c58c8605609316d3cb9fae2aa02c72c635adae",
    "bge-reranker": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
}


def main():
    models = {**EMBEDDERS, **RERANKERS}
    parser = argparse.ArgumentParser(description="Скачать открытые веса кандидатов в локальный кэш")
    parser.add_argument("models", nargs="+", choices=(*models, "all"))
    parser.add_argument("--output-dir", type=Path, default=Path(".cache/models"))
    args = parser.parse_args()
    names = models if "all" in args.models else dict.fromkeys(args.models)
    for name in names:
        path = snapshot_download(
            models[name], revision=REVISIONS[name], local_dir=args.output_dir / name,
            allow_patterns=[
                "model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json",
                "special_tokens_map.json", "*.model", "vocab.txt", "vocab.json", "merges.txt",
                "config_sentence_transformers.json", "sentence_bert_config.json", "1_Pooling/config.json",
            ],
        )
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
