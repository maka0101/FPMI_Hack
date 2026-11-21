# Кандидаты для поиска по почте VK

Ветка сравнивает три новых энкодера с готовым гибридом BM25 + E5. В обеих ветках поиска фильтр применяется до top‑K. Все энкодеры видят одинаковый исходный текст письма и получают лимит 512 токенов. Используются префиксы и способ объединения токенов из конфигурации конкретной модели.

| Модель | Протокол | Зачем включили |
|---|---|---|
| `intfloat/multilingual-e5-small` | Среднее по токенам, `query:` и `passage:`, 384 измерения | Контроль из первого прототипа. [Карточка модели](https://huggingface.co/intfloat/multilingual-e5-small) |
| `ibm-granite/granite-embedding-97m-multilingual-r2` | CLS, без префиксов, 384 измерения | В одном протоколе IBM получил 60,3 на multilingual retrieval против 50,9 у E5-small. Серверную задержку измеряем отдельно. [Карточка модели](https://huggingface.co/ibm-granite/granite-embedding-97m-multilingual-r2) · [Table 5 отчёта IBM](https://arxiv.org/html/2605.13521) |
| `deepvk/USER2-small` | Среднее по токенам, `search_query:` и `search_document:`, 384 измерения | Лёгкий русский энкодер, 34M параметров. Разработчики публикуют 61,87 на своём MTEB-rus Retrieval. [Карточка VK](https://huggingface.co/deepvk/USER2-small) |
| `microsoft/harrier-oss-v1-270m` | Последний токен, инструкция `web_search_query` для запроса, 640 измерений | Более крупный кандидат, 66,4 в той же таблице IBM. [Карточка Microsoft](https://huggingface.co/microsoft/harrier-oss-v1-270m) · [Table 5 отчёта IBM](https://arxiv.org/html/2605.13521) |

`RuModernBERT-base-reranker-ru` и `bge-reranker-v2-m3` получают одинаковые первые 20 кандидатов гибрида на Granite. Обе модели скорят пары «запрос — письмо» и переупорядочивают кандидатов по логиту. Для обоих ранжировщиков лимит пары 512 токенов. Пустые выдачи и выдачи из одного кандидата обходятся без вызова cross-encoder. [RuModernBERT](https://huggingface.co/n-bor1sov/RuModernBERT-base-reranker-ru) · [BGE](https://huggingface.co/BAAI/bge-reranker-v2-m3)

В официальном перечне multilingual E5 есть `small`, `base`, `large` и `large-instruct`. Granite 311M, USER2-base и USER-bge-m3 дают следующие точки для сравнения размера и качества на этой же текстовой архитектуре. [Линейка Microsoft E5](https://github.com/microsoft/unilm/tree/master/e5) · [Granite 311M](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2) · [USER2-base](https://huggingface.co/deepvk/USER2-base) · [USER-bge-m3](https://huggingface.co/deepvk/USER-bge-m3)

Для других сценариев Jina v3.5 оценивает список кандидатов совместно, `pplx-embed-v2-late-0.6b` сопоставляет токены через MaxSim, а `mSlideOn` добавляет обучаемую лексическую ветку. EmbeddingGemma 2 даёт общие эмбеддинги текста и изображений, поэтому подходит для отдельной проверки поиска по сканам. Jina v5 nano — дополнительный компактный текстовый энкодер на 239M. [Jina v3.5](https://huggingface.co/jinaai/jina-reranker-v3.5) · [Late interaction](https://huggingface.co/perplexity-ai/pplx-embed-v2-late-0.6b) · [mSlideOn](https://huggingface.co/blog/lightonai/slideon-mslideon) · [EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2) · [Jina v5 nano](https://jina.ai/en-US/models/jina-embeddings-v5-text-nano/)

## Протокол

Сравниваются 99 исходных запросов и 99 соответствующих перефразировок. Для обеих групп считаются Recall@10, nDCG@10 и серверный p99 через `/api/search`. Дополнительная группа из 99 перефразировок без дня сохраняет ящик, дату отсчёта и известные целевые письма. Для неё публикуются полнота по этим известным целям и p99. Из-за неполной разметки запросов без дня nDCG для этой группы не рассчитывается.

В каждом режиме один клиент после прогрева делает по три прохода. Это 297 вызовов на строку измерения задержки. Время включает токенизацию, инференс, работу индексов, RRF, cross-encoder при его наличии и сериализацию ответа. У E5 сохранён исходный ONNX INT8 на CPU. У остальных кандидатов отчёты указывают фактическое устройство и точность. Внешние MTEB/rusBEIR оценки приведены как мотивация эксперимента. Решение по почте принимается по локальному тесту.

## Результаты первого этапа

Замер сделан на Apple M4 Pro. PyTorch 2.15.0 и Transformers 4.57.6 использованы для новых моделей в BF16 на MPS. В столбце p99 указано наибольшее из трёх значений по группам запросов.

| Поиск | Исходные Recall@10 / nDCG@10 | Перефразы Recall@10 / nDCG@10 | Без дня, Recall@10 по известным целям | p99, мс | Чеки вне top‑50 BM25, найдено в top‑10 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0,9249 / 0,9785 | 0,6236 / 0,6351 | 0,1482 | 8,17 | 0/18 |
| [BM25 + E5-small](ml-e5.json) | 0,9187 / 0,9696 | 0,8246 / 0,8249 | 0,2109 | 13,43 | 10/18 |
| [BM25 + Granite 97M](ml-granite97.json) | 0,9158 / 0,9723 | 0,8024 / 0,8144 | 0,2351 | 14,54 | 9/18 |
| [BM25 + USER2-small](ml-user2-small.json) | 0,8984 / 0,9539 | 0,8102 / 0,7971 | 0,2213 | 20,28 | 8/18 |
| [BM25 + Harrier 270M](ml-harrier270.json) | 0,9279 / 0,9815 | 0,8225 / 0,8278 | 0,2071 | 24,98 | 9/18 |

## Результаты второго этапа

Хеш упорядоченных top‑20 одинаков у обоих ранжировщиков. Для сравнения показаны метрики Granite из прогона RuModernBERT. Метрики качества этого же первого этапа совпали в прогоне BGE.

| Поиск | Исходные Recall@10 / nDCG@10 | Перефразы Recall@10 / nDCG@10 | Без дня, Recall@10 по известным целям | p99, мс | Чеки вне top‑50 BM25, найдено в top‑10 |
|---|---:|---:|---:|---:|---:|
| BM25 + Granite 97M | 0,9158 / 0,9723 | 0,8024 / 0,8144 | 0,2351 | 14,89 | 9/18 |
| [Granite + RuModernBERT](ml-granite-ru-reranker.json) | 0,9196 / 0,9630 | 0,8094 / 0,8115 | 0,2505 | 540,02 | 9/18 |
| [Granite + BGE](ml-granite-bge-reranker.json) | 0,9265 / 0,9726 | 0,8245 / 0,8378 | 0,2627 | 1 235,37 | 10/18 |

Harrier лидирует по nDCG@10 среди гибридов первого этапа на исходных запросах и перефразировках с датой. Granite лидирует среди них по полноте известных целей без дня. RuModernBERT увеличил полноту Granite, но снизил nDCG@10 на датированных запросах. BGE улучшил nDCG@10 перефразировок на 2,34 п. п. относительно Granite, однако превысил лимит серверной задержки в 1 секунду в каждой группе.
