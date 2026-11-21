# Профили энкодеров и индексы писем

ML-процесс обслуживает один профиль из `models/profiles/<profile_id>.yaml`. Профиль задаёт кодировщик для писем и запросов. Для смены подготовленной модели переключите `MODEL_PROFILE` у backend и `--profile` у ML, перезапустите процессы и сверьте ответ `/readyz`. Изменения в коде backend для этого не требуются. [Контракт кандидатов](../contracts/ml-search-v1.md)

| Профиль | Что кодирует | Размерность | Подготовка |
|---|---|---:|---|
| `encoder-a` | Частоты слов после приведения к нижнему регистру и замены «ё» на «е», знаковое хеширование | 384 | CPU, 0 обученных параметров |
| `encoder-b` | Частоты слов и трёхбуквенных фрагментов, знаковое хеширование | 512 | CPU, 0 обученных параметров |
| `e5-small` | Обученный многоязычный энкодер E5. Письмо получает префикс `passage: `, запрос — `query: ` | 384 | CPU, 117,65 млн параметров, нужны локальные веса |

Первые два профиля воспроизводят путь от построения векторов до выдачи без загрузки весов. Поиск использует скалярное произведение. При `normalize: true` и ненулевых векторах оно равно косинусному сходству. Шаблон `{doc}` включает полный исходный текст письма с темой, если она есть. `max_length` ограничивает число слов у встроенных кодировщиков и число токенов у E5. Для всех трёх профилей установлен предел 256.

## Первый запуск

Из корня репозитория создайте окружение и постройте индекс для небольшого корпуса из шести писем. Запустите ML в этом же окружении.

```sh
uv sync --locked --python 3.11
source .venv/bin/activate
python -m mail_search --data tests/fixtures prepare --profiles encoder-a,encoder-b
python -m mail_search.ml --data tests/fixtures --profile encoder-a --port 8001
```

В другом терминале вызовите `curl -fsS http://127.0.0.1:8001/readyz`. Ответ содержит `status: ready`, `document_count: 6`, профиль, хеш корпуса и версию фактически открытого индекса. Для полного корпуса замените `tests/fixtures` на `mipt_mail_search_participants` в обеих командах. Для сравнения профилей используйте один набор запросов, дату, K и оборудование. [Команды и формат отчёта](experiments.md)

## Локальные веса E5

Профиль закрепляет модель и токенизатор `intfloat/multilingual-e5-small` на коммите `614241f622f53c4eeff9890bdc4f31cfecc418b3`. Веса в репозиторий не входят. Однократно скачайте файлы из этой ревизии на машине с доступом в интернет. Загрузка требует около 490 МБ на диске для модели и токенизатора. [Карточка модели и лицензия MIT](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3)

```sh
uv sync --locked --python 3.11 --extra transformers
source .venv/bin/activate
python - <<'PY'
import os
from pathlib import Path
from huggingface_hub import snapshot_download
from mail_search.ml_profiles import read_profile

profile = read_profile("e5-small")
snapshot_download(
    repo_id=profile.model_id,
    revision=profile.model_revision,
    local_dir=Path(os.getenv("ARTIFACT_DIR", ".artifacts")) / profile.weights_dir,
    allow_patterns=list(profile.files_sha256),
)
PY
HF_HUB_OFFLINE=1 python -m mail_search --data tests/fixtures prepare --profiles e5-small
HF_HUB_OFFLINE=1 python -m mail_search.ml --data tests/fixtures --profile e5-small
```

Для Compose скопируйте `weights/e5-small/` внутрь каталога, заданного `ML_ARTIFACTS`; по умолчанию это `.artifacts/`. Подготовьте индекс в том же образе, в котором запускается сервис. [Конфигурация Compose и переключение моделей](../infrastructure.md)

```sh
INSTALL_TRANSFORMERS=1 docker compose run --build --rm --no-deps ml \
  python -m mail_search prepare --profiles e5-small
SEARCH_MODE=encoder MODEL_PROFILE=e5-small INSTALL_TRANSFORMERS=1 \
  docker compose --profile semantic up --build -d --wait
```

## Новый профиль

Скопируйте YAML ближайшей модели под новым именем. Имя файла без расширения должно совпасть с `profile_id`. Для нового энкодера в формате Sentence Transformers, который выдаёт один фиксированный вектор на текст, достаточно существующего адаптера `sentence-transformers`.

| Поле | Значение |
|---|---|
| `adapter` | `word-hash`, `subword-hash` или `sentence-transformers` |
| `model_id`, `model_revision` | Идентификатор весов и ревизия. Для Sentence Transformers нужен полный Git SHA из 40 шестнадцатеричных символов |
| `tokenizer_id`, `tokenizer_revision` | Источник и ревизия токенизатора. Его файлы должны находиться в локальном каталоге снапшота рядом с моделью |
| `parameter_count`, `dimensions` | Число обученных параметров и длина одного вектора. При запуске размерность сверяется с выходом модели |
| `document_template`, `query_prefix` | Шаблон с одним вхождением `{doc}` и строка перед исходным текстом запроса. Учитывайте пробел после префикса |
| `max_length`, `normalize` | Длина входа и L2-нормализация |
| `weights_dir`, `files_sha256` | Для Sentence Transformers — путь к локальному снапшоту относительно `ARTIFACT_DIR` и таблица контрольных сумм всех файлов, нужных для инференса. Включите веса, конфигурацию слоёв и токенизатор |

Подготовьте каталог весов, затем выполните `prepare --profiles <profile_id>`. Сервис загружает модель только из этого каталога, с `device="cpu"`, `local_files_only=True` и `trust_remote_code=False`. Изменения способа кодирования во встроенном адаптере требуют обновления ревизии профиля или версии формата индекса.

## Содержимое кэша и проверка готовности

`PROFILE_DIR` по умолчанию указывает на `models/profiles`, `ARTIFACT_DIR` — на `.artifacts`. Готовый индекс хранится в `ARTIFACT_DIR/indexes/<index_version>/`. В `vectors.npy` лежит матрица float32, в `rows.json` — соответствие номера строки, doc_id, ящика и даты. `manifest.json` содержит размеры корпуса, конфигурацию построения, версии библиотек и SHA-256 файлов индекса.

| Изменение | Что произойдёт |
|---|---|
| Байты `documents.jsonl`, версия модели или токенизатора, контрольные суммы весов, шаблон письма, длина, размерность, нормализация, адаптер | Изменится `index_version`. Нужен новый `prepare` |
| Версия NumPy, а у Sentence Transformers также версии Sentence Transformers, Transformers, Torch или Tokenizers | Изменится ключ индекса. Локальная сборка Torch и Linux CPU могут иметь разные версии. Выполняйте `prepare` в целевом окружении |
| Префикс запроса | Индекс переиспользуется, меняется `profile_sha256`. Для применения перезапустите ML и backend |
| K, режим BM25/encoder/hybrid, дата или ящик запроса | Используется тот же индекс |
| Возврат к прежнему профилю и корпусу | Проверяется и открывается ранее подготовленный индекс |

Сборка использует временный каталог на том же томе и публикует готовый индекс одним переименованием. Блокировка сериализует одновременные сборки одного ключа. При повторном вызове `prepare` проверяет манифест и SHA-256 матрицы и таблицы строк. Для восстановления повреждённого кэша переместите каталог соответствующей версии в резервную копию, повторите `prepare` и перезапустите сервис.

При старте ML сверяет корпус, профиль и артефакты, открывает матрицу, проверяет SHA-256 файлов модели и выполняет один прогревочный запрос. Отсутствующий или несовместимый индекс даёт HTTP 503 на `/readyz`. Адрес `/healthz` показывает доступность самого процесса. После подготовки ранее отсутствовавшего индекса перезапустите ML. Поиск ограничивает список строк ящиком и допустимыми датами до оценки кандидатов, при равенстве score сортирует по doc_id. Для письма с неизвестной датой доступен запрос без ограничения на конкретный день.
