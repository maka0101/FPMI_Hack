"use strict";

const get = id => document.getElementById(id);
const source = get("source");
const mailbox = get("mailbox");
const asOf = get("as-of");
const query = get("query");
const status = get("status");
const heading = get("heading");
const condition = get("condition");
const rows = get("rows");
const actions = get("actions");
const reader = get("reader");
const message = get("message");
const help = "Для поиска по ориентиру бэкенду нужны GET /api/search с dated_only=true и POST /api/search/nearby.";
const demoMailbox = "Казань · демо";
const demoDate = "2026-05-24";
const demoMail = [
  ["estimate-before", "2026-05-10", "Смета на ремонт кухни", "Предварительный расчёт работ после замеров."],
  ["ticket", "2026-05-12", "Билеты в Казань — заказ подтверждён", "Покупка билетов подтверждена. Москва → Казань. Вылет 15 мая."],
  ["estimate-same", "2026-05-12", "Смета на ремонт квартиры", "Обновили расчёт работ и материалов. Пришлите удобную дату начала ремонта."],
  ["registration", "2026-05-14", "Регистрация на рейс в Казань", "Открылась регистрация на рейс по вашим билетам."],
  ["estimate-after", "2026-05-14", "Смета на ремонт ванной", "В расчёт вошли демонтаж, подготовка стен и укладка плитки."],
  ["contract", "2026-05-16", "Договор на участие в конференции", "Подпишите договор и пришлите скан организатору."],
  ["invitation", "2026-05-17", "Приглашение на встречу", "Приглашаем обсудить программу конференции в Казани."],
  ["return", "2026-05-18", "Обратный билет Казань — Москва", "Покупка билета подтверждена. Маршрутная квитанция во вложении."],
  ["estimate-final", "2026-05-23", "Финальная смета на ремонт", "Уточнили стоимость материалов. Финальный расчёт во вложении."],
  ["venue", "2026-05-02", "Адрес конференции в Казани", "Конференция пройдёт в Казани. Адрес площадки — ул. Кремлёвская, 1."]
].map(([doc_id, day, subject, body]) => ({ doc_id, day, subject, preview: body, body }));

let boxes = {};
let submitted = "";
let searchVersion = 0;
let messageVersion = 0;
let activeRow = null;

function parse(text) {
  const clean = value => value.trim().replace(/[.!?]+$/, "").trim();
  const browse = text.match(/^письма\s+рядом\s+с\s+(.+)$/iu);
  if (browse) return { target: "", event: clean(browse[1]), direction: "around" };
  const parts = [...text.matchAll(/\s+(после|до)\s+письма\s+(?:про\s+|о\s+|об\s+|с\s+)?|[\s.,]+(?:я\s+)?примерно\s+(?:тогда(?:\s+же)?|в\s+то\s+же\s+время)(?:,?\s+когда)?\s+/giu)];
  if (parts.length !== 1) return null;
  const [separator, relation] = parts[0];
  const target = clean(text.slice(0, parts[0].index).replace(/^ищу\s+/iu, ""));
  const event = clean(text.slice(parts[0].index + separator.length)
    .replace(/^пришло\s+письмо\s+(?:про\s+|о\s+|об\s+|с\s+)?/iu, ""));
  if (!target || !event) return null;
  const direction = { до: "before", после: "after" }[relation?.toLowerCase()] || "around";
  return { target, event, direction };
}

async function request(path, params = {}, payload) {
  const url = new URL(path, location.origin);
  url.search = new URLSearchParams(params);
  const options = { signal: AbortSignal.timeout(8000) };
  if (payload) Object.assign(options, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.error || "Ошибка почтового API"), { status: response.status });
  return { data, headers: response.headers };
}

const dayNumber = date => Date.parse(date + "T00:00:00Z") / 86400000;
const dateString = day => new Date(day * 86400000).toISOString().slice(0, 10);
const displayDate = day => day ? new Intl.DateTimeFormat("ru", {
  day: "numeric", month: "long", year: "numeric", timeZone: "UTC"
}).format(new Date(day + "T00:00:00Z")) : "Дата неизвестна";

function demoMatches(text, candidates) {
  const words = (text.toLowerCase().match(/[\p{L}\p{N}]+/gu) || [])
    .filter(word => word.length >= 4 && !["письмо", "пришло", "когда", "которую"].includes(word))
    .map(word => word.slice(0, 4));
  return candidates.map(item => ({
    item,
    score: words.reduce((score, word) => {
      if (item.subject.toLowerCase().includes(word)) return score + 2;
      return score + Number(item.preview.toLowerCase().includes(word));
    }, 0)
  })).filter(({ score }) => !words.length || score);
}

function demoNearby(context, intent, anchor, size) {
  const day = dayNumber(anchor.day);
  const from = day - (intent.direction === "after" ? 0 : size);
  const to = Math.min(dayNumber(context.as_of), day + (intent.direction === "before" ? 0 : size));
  const eligible = demoMail.filter(item => item.doc_id !== anchor.doc_id &&
    dayNumber(item.day) >= from && dayNumber(item.day) <= to);
  const results = demoMatches(intent.target, eligible).map(({ item, score }) => ({
    item: { ...item, delta_days: dayNumber(item.day) - day }, score
  })).sort((a, b) => b.score - a.score ||
    Math.abs(a.item.delta_days) - Math.abs(b.item.delta_days) ||
    a.item.doc_id.localeCompare(b.item.doc_id));
  return { window: { from: dateString(from), to: dateString(to) }, results: results.slice(0, 10).map(row => row.item) };
}

function closeMessage(restoreFocus = false) {
  ++messageVersion;
  reader.classList.remove("reading");
  message.replaceChildren(node("p", "Выберите письмо из списка."));
  if (restoreFocus) activeRow?.focus();
}

function node(tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function start(label) {
  const version = ++searchVersion;
  closeMessage();
  activeRow = null;
  rows.replaceChildren();
  actions.replaceChildren();
  condition.hidden = true;
  heading.textContent = label;
  status.textContent = "";
  return version;
}

function action(label, handler) {
  const button = node("button", label, "link");
  button.type = "button";
  button.addEventListener("click", handler);
  actions.append(button);
}

function relative(delta) {
  if (delta === 0) return "В тот же день";
  const count = Math.abs(delta);
  const unit = new Intl.PluralRules("ru").select(count) === "few" ? "дня" : "дней";
  const amount = count === 1 ? "день" : count + " " + unit;
  return delta < 0 ? "За " + amount + " до" : "Через " + amount;
}

function renderRows(items, select) {
  for (const item of items) {
    const row = node("button", "", "row");
    row.type = "button";
    row.append(node("strong", item.subject || "Без темы"),
      node("small", displayDate(item.day), "meta"), node("span", item.preview || ""));
    if (Number.isInteger(item.delta_days)) row.append(node("small", relative(item.delta_days), "relative"));
    row.addEventListener("click", () => select(item, row));
    rows.append(row);
  }
}

function describeError(error) {
  return error.name === "TimeoutError" ? "Сервер не ответил вовремя." :
    error instanceof TypeError || error instanceof SyntaxError ? "Не удалось получить ответ почтового API." : error.message;
}

async function openMessage(context, item, row) {
  const version = ++messageVersion;
  activeRow?.removeAttribute("aria-current");
  activeRow = row;
  row.setAttribute("aria-current", "true");
  reader.classList.add("reading");
  message.replaceChildren(node("h2", "Открываем письмо…"));
  const headingInReader = message.firstElementChild;
  headingInReader.tabIndex = -1;
  headingInReader.focus({ preventScroll: true });
  try {
    const mail = context.demo ? demoMail.find(entry => entry.doc_id === item.doc_id) :
      (await request("/api/message", { ...context.scope, doc_id: item.doc_id })).data;
    if (version !== messageVersion) return;
    headingInReader.textContent = mail.subject || "Без темы";
    message.append(node("p", displayDate(mail.day), "meta"), node("pre", mail.body));
  } catch (error) {
    if (version !== messageVersion) return;
    headingInReader.textContent = "Письмо не открылось";
    const retry = node("button", "Повторить", "link");
    retry.addEventListener("click", () => openMessage(context, item, row));
    message.append(node("p", describeError(error)), retry);
  }
}

async function ordinary(context, text) {
  const version = start("Ищем письма…");
  try {
    const { data, headers } = context.demo ? {
      data: demoMatches(text, demoMail.filter(item => item.day <= context.scope.as_of))
        .sort((a, b) => b.score - a.score || b.item.day.localeCompare(a.item.day)).map(row => row.item)
    } : await request("/api/search", { ...context.scope, q: text });
    if (version !== searchVersion) return;
    heading.textContent = data.length ? (text ? "Результаты поиска" : "Последние письма") : "Письма не найдены";
    renderRows(data, (item, row) => openMessage(context, item, row));
    const day = headers?.get("X-Target-Day");
    const fallback = headers?.get("X-Search-Mode") === "bm25-fallback";
    status.textContent = "Писем: " + data.length + (day ? " · За " + displayDate(day) : "") +
      (fallback ? " · Поиск по словам" : "");
  } catch (error) {
    if (version !== searchVersion) return;
    heading.textContent = "Поиск недоступен";
    status.textContent = describeError(error);
    action("Повторить", () => ordinary(context, text));
  }
}

function demoAction() {
  action("Открыть демоданные", () => {
    source.value = "demo";
    loadSource();
  });
}

async function chooseAnchor(context, intent) {
  const version = start("Ищем письма об этом событии…");
  try {
    const candidates = context.demo ?
      demoMatches(intent.event, demoMail.filter(item => item.day <= context.scope.as_of))
        .sort((a, b) => b.score - a.score).slice(0, 3).map(row => row.item) :
      (await request("/api/search", { ...context.scope, q: intent.event, limit: 3, dated_only: true })).data;
    if (version !== searchVersion) return;
    if (!Array.isArray(candidates) || candidates.some(item => !item.day || item.day > context.scope.as_of)) {
      throw new Error("Ответ поиска ориентиров нарушает условия по дате.");
    }
    if (candidates.length) {
      heading.textContent = {
        before: "До какого письма искать?",
        after: "После какого письма искать?",
        around: "Какое письмо поможет вспомнить дату?"
      }[intent.direction];
      status.textContent = intent.target ? "Ищем «" + intent.target + "»" : "Ищем соседние письма";
      renderRows(candidates.slice(0, 3), item => nearby(context, intent, item, 3));
    } else {
      heading.textContent = "Не нашли письмо об этом событии";
      if (!context.demo) {
        status.textContent = help;
        demoAction();
      }
      action("Изменить запрос", () => query.focus());
    }
    action("Искать всю фразу", () => ordinary(context, context.text));
    heading.focus();
  } catch (error) {
    if (version !== searchVersion) return;
    heading.textContent = "Поиск по ориентиру недоступен";
    status.textContent = describeError(error) + " " + help;
    action("Повторить", () => chooseAnchor(context, intent));
    action("Искать всю фразу", () => ordinary(context, context.text));
    demoAction();
    heading.focus();
  }
}

async function nearby(context, intent, anchor, size) {
  const version = start("Ищем письма по дате…");
  try {
    const data = context.demo ? demoNearby(context.scope, intent, anchor, size) :
      (await request("/api/search/nearby", {}, {
        ...context.scope, q: intent.target, anchor_doc_id: anchor.doc_id,
        direction: intent.direction, window_days: size, limit: 10
      })).data;
    if (version !== searchVersion) return;
    const relation = { before: "до", after: "после", around: "вокруг даты" }[intent.direction];
    const topic = intent.target || "Соседние письма";
    condition.textContent = topic + " · " + displayDate(data.window.from) + " — " +
      displayDate(data.window.to) + " · " + relation + " письма «" + (anchor.subject || "Без темы") + "»";
    condition.hidden = false;
    heading.textContent = data.results.length ? "Результаты поиска" : "В пределах " + size + " дней ничего не найдено";
    status.textContent = "Писем: " + data.results.length;
    renderRows(data.results, (item, row) => openMessage(context, item, row));
    if (!data.results.length && size === 3) action("Расширить до 7 дней", () => nearby(context, intent, anchor, 7));
    action("Сменить письмо", () => chooseAnchor(context, intent));
    if (!data.results.length && size === 7 && intent.target) {
      action("Искать во всём ящике", () => ordinary(context, intent.target));
    }
  } catch (error) {
    if (version !== searchVersion) return;
    heading.textContent = "Поиск по дате недоступен";
    status.textContent = describeError(error) + " " + help;
    if (error.status !== 400 && error.status !== 404) action("Повторить", () => nearby(context, intent, anchor, size));
    action("Сменить письмо", () => chooseAnchor(context, intent));
    if (error.status === 400) action("Изменить запрос", () => query.focus());
    if (intent.target) action("Искать во всём ящике", () => ordinary(context, intent.target));
    demoAction();
  }
  heading.focus();
}

function runSearch() {
  if (!mailbox.value || !asOf.value) return;
  const context = { demo: source.value === "demo", scope: { mailbox: mailbox.value, as_of: asOf.value }, text: submitted };
  const intent = parse(submitted);
  if (intent) chooseAnchor(context, intent);
  else ordinary(context, submitted);
}

function resetDate() {
  const today = new Date();
  const localDate = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  asOf.value = boxes[mailbox.value] || localDate;
}

async function loadSource() {
  const version = start("Загружаем ящики…");
  const demo = source.value === "demo";
  mailbox.replaceChildren();
  asOf.value = "";
  get("submit").disabled = true;
  get("source-note").textContent = demo ? "Демоданные. Поиск и чтение выполняются на вымышленных письмах." : "";
  try {
    const loadedBoxes = demo ? { [demoMailbox]: demoDate } : (await request("/api/mailboxes")).data;
    if (version !== searchVersion) return;
    boxes = loadedBoxes;
    for (const name of Object.keys(boxes)) mailbox.add(new Option(name, name));
    if (!mailbox.value) {
      heading.textContent = "Нет доступных ящиков";
      if (!demo) demoAction();
      return;
    }
    resetDate();
    get("submit").disabled = false;
    runSearch();
  } catch (error) {
    if (version !== searchVersion) return;
    heading.textContent = "Не удалось загрузить ящики";
    status.textContent = describeError(error);
    action("Повторить", loadSource);
    if (!demo) demoAction();
  }
}

get("search").addEventListener("submit", event => {
  event.preventDefault();
  submitted = query.value.trim();
  runSearch();
});
mailbox.addEventListener("change", () => { resetDate(); runSearch(); });
asOf.addEventListener("change", () => {
  if (asOf.value) runSearch();
  else start("Выберите дату отсчёта");
});
source.addEventListener("change", loadSource);
get("back").addEventListener("click", () => closeMessage(true));
rows.addEventListener("keydown", event => {
  if (event.key === "Escape") query.focus();
  const choices = [...rows.querySelectorAll("button")];
  if (!choices.includes(event.target) || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
  event.preventDefault();
  const step = event.key === "ArrowDown" ? 1 : -1;
  choices[(choices.indexOf(event.target) + step + choices.length) % choices.length].focus();
});
for (const button of document.querySelectorAll("[data-example]")) {
  button.addEventListener("click", () => {
    query.value = submitted = button.dataset.example;
    source.value = "demo";
    loadSource();
  });
}
if (new URLSearchParams(location.search).get("demo") === "1") source.value = "demo";
loadSource();
