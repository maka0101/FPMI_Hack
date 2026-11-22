---
theme: default
layout: default
title: Умный поиск в Почте
info: Защита решения кейса VK Tech на хакатоне ФПМИ
author: Команда FPMI_Hack
lang: ru
duration: 3min
canvasWidth: 1120
aspectRatio: 16/9
fonts:
  provider: none
  sans: Arial
  serif: Georgia
  mono: Menlo
drawings:
  enabled: false
---

<div class="mail-cover">
<div class="brand">ФПМИ <i></i> Кейс VK Tech</div>
<h1>Умный поиск<br>в Почте</h1>
<p class="intro">Как найти письмо, если помнишь только событие и примерное время?</p>
<div class="envelope" aria-hidden="true"><div class="letter"><strong>Входящие</strong><span>Уведомление о выгрузке</span><b></b><b></b></div><div class="flap"></div></div>
<div class="foot">Веб-прототип · поиск по письмам и датам</div>
</div>

<!-- Начните с истории про вчерашнюю выгрузку. Цель пользователя — открыть исходное письмо. -->

---

<div class="scene">
<div class="eyebrow">Поиск по корпусу хакатона</div>
<h1>«Где вчера писали о выгрузке?»</h1>
<div class="screen-grid"><div class="shot"><img src="/corpus-search.png" alt="Веб-интерфейс с найденными письмами о выгрузке и открытым письмом"></div>
<div class="aside"><strong>14 → 13 сентября</strong><p>«Вчера» отсчитывается от даты запроса.</p><strong>Один ящик</strong><p>Открываем исходное письмо прямо из выдачи.</p></div></div>
<div class="foot">Снимок работающего интерфейса · Почтовый API · сентябрь 2028 года в наборе</div>
</div>

<!-- Показать запрос, дату и открытое письмо. При живом показе использовать точную строку и ящик из speech.md. -->

---

<div class="scene">
<div class="eyebrow">Поиск по событию · демонстрационный ящик</div>
<h1>«Смета пришла после покупки билетов»</h1>
<div class="screen-grid"><div class="shot"><img src="/event-timeline.png" alt="Хронология почты рядом с письмом о билетах в Казань"></div>
<div class="aside"><strong>Билет в Казань</strong><p>Письмо от 12 мая становится ориентиром.</p><strong>Почта рядом</strong><p>Можно уточнить период или открыть соседние письма.</p></div></div>
<div class="foot">Сценарий интерфейса v2 · демоданные для показа хронологии</div>
</div>

<!-- Переключитесь в демоящик. Выберите билет от 12 мая и откройте хронологию. -->

---

<div class="scene">
<div class="eyebrow">Как устроен штатный поиск</div>
<h1>Два способа прочитать один запрос</h1>
<div class="pipeline">
<div class="entry"><b>Ящик и период</b><span>Парсер выделяет даты.<br>Будущие письма исключаются.</span></div>
<div class="fork"><div><b>BM25</b><span>Слова в теме и тексте</span><em>85%</em></div><div><b>Harrier 270M</b><span>Близость по смыслу</span><em>15%</em></div></div>
<div class="out"><b>Топ-10</b><span>Объединяем позиции<br>в двух списках.</span></div>
</div>
<p class="under">Векторы писем считаются заранее. При поиске модель кодирует только запрос.</p>
<div class="foot">SQLite FTS5 + локальный ML-сервис · до 50 кандидатов от каждой ветви при выдаче десяти писем</div>
</div>

<!-- Стрелки ведут от ограничений запроса к двум параллельным ветвям. Проценты — веса голосов за место письма. -->

---

<div class="scene">
<div class="eyebrow">Что даёт смысловой поиск</div>
<h1>Нужное письмо поднялось на первое место</h1>
<p class="sub">Тот же запрос о выгрузке контейнеров. Места двух писем в сохранённом прогоне.</p>
<table class="rank"><thead><tr><th>Письмо</th><th>По словам</th><th>По смыслу</th><th>Вместе</th></tr></thead>
<tbody><tr class="winner"><td>Нужное по разметке</td><td>2</td><td>1</td><td><b>1</b></td></tr><tr><td>Другой кандидат</td><td>1</td><td>8</td><td>2</td></tr></tbody></table>
<p class="under">Высокая позиция по смыслу изменила порядок первых двух писем.</p>
<div class="foot">Публичный запрос H-124bc9656e09acbcf2fc · релевантное письмо L-74f3dc91fce6d46520ba</div>
</div>

<!-- Прочитайте только первую строку и укажите на восьмое место конкурента. -->

---

<div class="scene">
<div class="eyebrow">Что измерили · штатный гибрид</div>
<h1>93,5% нужных писем в первой десятке</h1>
<p class="sub">Средняя полнота на 99 публичных запросах. На свободных формулировках задача сложнее.</p>
<div class="scores"><div><span>Набор</span><span>Recall@10</span><span>nDCG@10</span></div><div><b>Публичные · 99</b><b>0,9354</b><b>0,9883</b></div><div><b>Перефразировки с датой · 32</b><b>0,7116</b><b>0,6741</b></div></div>
<p class="under">Recall измеряет полноту, nDCG учитывает порядок. Веса выбирали на публичных 99.</p>
<div class="foot">Корпус организаторов · 16 376 писем · 565 размеченных связей в публичном наборе</div>
</div>

<!-- Приведите число 93,5% и поясните, что это средняя доля найденных писем. Вторую строку используйте для разговора об ограничениях. -->

---

<div class="scene finish">
<div class="eyebrow">Работающий прототип</div>
<h1>Найденное письмо можно<br>открыть и проверить</h1>
<div class="proof"><div class="number">18,8 <small>мс</small></div><div><b>Серверный p99 на локальном прогоне</b><span>297 запросов · Apple M4 Pro · порог кейса &lt; 1 секунды</span></div></div>
<p class="closing">В репозитории — веб-интерфейс, локальный ML-сервис, экспорт ранжированных ID и инструкция запуска.</p>
<div class="foot"><a href="https://github.com/maka0101/FPMI_Hack">github.com/maka0101/FPMI_Hack</a></div>
</div>

<!-- Закрыть демонстрацию. Предложить жюри проверить выдачу или разобрать конкретный запрос. -->
