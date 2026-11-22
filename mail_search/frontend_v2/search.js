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
const demoMailbox = "Личный ящик · демо";
const demoDate = "2026-06-06";
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
  ["venue", "2026-05-02", "Адрес конференции в Казани", "Конференция пройдёт в Казани. Адрес площадки — ул. Кремлёвская, 1."],

  ["hotel-payment", "2026-05-03", "Чек за проживание в отеле Утёс", "Получили оплату 12 400 ₽ за две ночи. Кассовый чек приложен к письму."],
  ["hotel-booking", "2026-05-04", "Бронь отеля Утёс в Сочи", "Подтверждаем проживание с 22 по 24 мая. Заезд с 15:00, выезд до полудня."],
  ["hotel-transfer", "2026-05-05", "Трансфер до отеля Утёс", "Водитель встретит у выхода из зала прилёта. Путь до отеля займёт около 35 минут."],
  ["train-tver", "2026-04-09", "Билет на поезд в Тверь", "Отправление с Ленинградского вокзала 19 апреля в 08:40. Вагон 6, место 22."],
  ["train-refund", "2026-04-12", "Возврат билета на поезд в Тверь", "Деньги за отменённую поездку вернутся на исходную карту в течение пяти рабочих дней."],
  ["museum-route", "2026-04-13", "Маршрут по музеям Твери", "Начнём с картинной галереи, потом зайдём в музей фотографии. Сбор у входа в 11:00."],
  ["passport-appointment", "2026-03-12", "Запись на подачу документов для загранпаспорта", "Ждём вас 19 марта в 10:30. Возьмите паспорт и оригиналы документов из заявления."],
  ["passport-fee", "2026-03-13", "Квитанция об оплате пошлины", "Платёж за оформление загранпаспорта принят. Электронная квитанция доступна во вложении."],

  ["shoe-order", "2026-05-19", "Заказ кроссовок принят", "Кроссовки 42 размера переданы на сборку. Доставка в пункт выдачи ожидается к пятнице."],
  ["shoe-courier", "2026-05-22", "Кроссовки готовы к выдаче", "Заказ лежит в пункте выдачи на улице Лесной. Забрать можно до 29 мая."],
  ["shoe-label", "2026-05-24", "Этикетка для возврата кроссовок", "Наклейте этикетку на коробку и передайте её в тот же пункт выдачи. Примерка не влияет на возврат."],
  ["kettle-order", "2026-04-23", "Чайник передан курьеру", "Курьер привезёт заказ завтра с 12:00 до 16:00. Проверьте комплект при получении."],
  ["kettle-warranty", "2026-04-25", "Гарантийный талон на чайник", "Гарантия действует 24 месяца со дня покупки. Сохраните талон вместе с кассовым чеком."],
  ["gift-card", "2026-03-27", "Электронный сертификат книжного магазина", "Сертификат на 2 000 ₽ можно использовать онлайн или в магазине до конца года."],
  ["market-receipt", "2026-05-20", "Чек за доставку продуктов", "В заказе 14 товаров. Деньги за отсутствующую упаковку клубники вернули на карту."],

  ["interview", "2026-05-06", "Приглашение на собеседование по аналитике", "Созвон с командой продукта состоится 8 мая в 11:00. Запланируйте 45 минут."],
  ["interview-task", "2026-05-08", "Тестовое задание по аналитике", "В таблице заказы за три месяца. Подготовьте расчёт повторных покупок и короткий вывод к понедельнику."],
  ["job-offer", "2026-05-13", "Предложение о работе · продуктовая аналитика", "Предлагаем начать 1 июня. Условия работы и список документов для оформления приложены."],
  ["signing-job", "2026-05-14", "Документы готовы к подписанию", "Пакет документов подготовлен. Проверьте данные и подпишите его до конца недели."],
  ["team-demo", "2026-04-17", "Демонстрация новой отчётности", "На пятничном созвоне покажем отчёт по обращениям и обсудим метрики поддержки."],
  ["team-notes", "2026-04-18", "Протокол обсуждения отчётности", "Согласовали сверку за апрель. Полина проверит выгрузку, Илья обновит отчёт к 24 апреля."],
  ["stand-access", "2026-04-02", "Доступ к тестовому стенду открыт", "У вашей команды есть доступ на чтение к журналу сборок. Для входа используйте рабочую учётную запись."],
  ["vendor-invoice", "2026-04-04", "Счёт за обслуживание тестового стенда", "Сумма за апрель — 8 900 ₽. Просьба указать номер счёта в назначении платежа."],
  ["office-pass", "2026-05-21", "Гостевой пропуск в офис на четверг", "Покажите паспорт на стойке регистрации. Пропуск действует до 19:00."],

  ["lease-draft", "2026-03-28", "Проект договора аренды квартиры", "Проверьте срок аренды и пункт о залоге. В договор включена мебель из описи."],
  ["lease-viewing", "2026-03-30", "Просмотр квартиры на Парковой", "Встречаемся у второго подъезда в 18:30. Домофон откроет менеджер."],
  ["signing-lease", "2026-03-31", "Документы готовы к подписанию", "Пакет документов подготовлен. Проверьте данные и подпишите его до конца недели."],
  ["lease-act", "2026-04-05", "Акт передачи ключей от квартиры", "Передано два комплекта ключей. Показания счётчиков внесены в акт."],
  ["meters", "2026-05-26", "Напоминание о показаниях счётчиков", "Показания воды и электричества можно передать до 28 мая через личный кабинет."],
  ["utility-bill", "2026-05-28", "Квитанция за коммунальные услуги", "В квитанции за май учтены переданные показания. Оплата до 10 июня."],
  ["internet-visit", "2026-04-07", "Подключение интернета · визит мастера", "Мастер придёт во вторник с 10:00 до 12:00. Освободите доступ к розетке у входа."],
  ["internet-contract", "2026-04-07", "Договор на домашний интернет", "Подключён тариф 300 Мбит/с. Ежемесячная оплата списывается 7-го числа."],

  ["dentist-booking", "2026-04-20", "Запись к стоматологу подтверждена", "Приём 22 апреля в 16:30. Если планы изменятся, перенесите запись заранее."],
  ["dentist-receipt", "2026-04-22", "Чек за приём стоматолога", "Клиника получила 3 500 ₽ за консультацию и снимок. Чек приложен."],
  ["dentist-certificate", "2026-04-23", "Справка для налогового вычета за лечение", "Подготовили справку об оплате медицинских услуг. Проверьте ФИО и сумму в документе."],
  ["lab-booking", "2026-03-09", "Подтверждение записи в лабораторию", "Ждём вас утром 11 марта. Условия подготовки указаны в памятке для выбранного анализа."],
  ["lab-result", "2026-03-11", "Результаты лабораторного исследования готовы", "Результаты доступны в личном кабинете. Если требуется расшифровка, запишитесь к врачу."],
  ["pool-intro", "2026-05-02", "Пробное занятие в бассейне", "Тренер встретит вас у стойки в 09:15. Возьмите шапочку и сменную обувь."],
  ["pool-plan", "2026-05-04", "Абонемент в бассейн на восемь занятий", "Абонемент действует 60 дней. Забронировать дорожку можно через администратора."],

  ["course-start", "2026-04-15", "Старт курса по фотографии", "Первый урок в среду в 19:30. Принесите камеру или телефон с ручными настройками."],
  ["course-payment", "2026-04-14", "Чек за курс по фотографии", "Оплата за четыре занятия прошла. Возврат оформляется через администратора курса."],
  ["course-homework", "2026-04-17", "Домашнее задание по фотографии", "Сделайте пять кадров с разной выдержкой. Загрузите их в папку группы до следующего урока."],
  ["school-meeting", "2026-05-06", "Родительское собрание в 5Б", "Собрание начнётся в 18:00 в кабинете 214. Обсудим расписание на конец четверти."],
  ["school-trip", "2026-05-07", "Согласие на школьную экскурсию", "Класс поедет в технический музей 20 мая. Подпишите согласие и передайте его классному руководителю."],
  ["library-hold", "2026-03-16", "Книга готова к выдаче в библиотеке", "«История фотографии» ждёт вас на стойке до пятницы. Для получения нужен читательский билет."],
  ["library-return", "2026-04-06", "Напоминание о возврате книги", "Срок выдачи истекает 8 апреля. Продлить книгу можно через личный кабинет библиотеки."],

  ["insurance-quote", "2026-03-21", "Расчёт стоимости страховки автомобиля", "Предложение действует до 25 марта. В расчёт включена помощь на дороге."],
  ["insurance-policy", "2026-03-24", "Электронный полис страхования автомобиля", "Полис вступает в силу 25 марта. Скачайте копию для хранения вместе с документами на машину."],
  ["insurance-payment", "2026-03-24", "Квитанция за автомобильную страховку", "Платёж получен. Номер полиса и сумма указаны в электронной квитанции."],
  ["card-statement", "2026-05-01", "Выписка по карте за апрель", "Выписка сформирована. Покупки и возвраты доступны в разделе истории операций."],
  ["savings-deposit", "2026-05-09", "Вклад открыт", "Срок вклада — три месяца. Первая выплата процентов назначена на 9 июня."],
  ["tax-letter", "2026-05-15", "Декларация принята к рассмотрению", "Уведомление о результате появится в личном кабинете после камеральной проверки."],

  ["concert-order", "2026-05-29", "Билет на джазовый концерт", "Концерт 12 июня в 20:00. Партер, ряд 4, место 11. Вход открывается за час."],
  ["concert-change", "2026-06-01", "Джазовый концерт перенесли на другую площадку", "Новый зал находится на Набережной, 7. Дата и время концерта прежние. Билет действителен."],
  ["concert-refund", "2026-06-04", "Условия возврата за джазовый концерт", "Из-за смены площадки можно оформить полный возврат до 10 июня через билетную кассу."],
  ["theatre", "2026-04-27", "Билеты на спектакль «Вишнёвый сад»", "Спектакль 3 мая в 19:00. Вход со стороны дворика. Продолжительность два часа с антрактом."],
  ["race-register", "2026-04-28", "Регистрация на забег на 5 км", "Вы записаны на майский забег. Номер участника можно получить в субботу утром."],
  ["race-route", "2026-04-30", "Схема маршрута майского забега", "Старт у входа в парк. Камеры хранения откроются в 07:30. Встречаемся у первой арки."],
  ["family-invite", "2026-05-08", "День рождения Лены в субботу", "Будем в кафе на Сиреневой в 17:00. Сообщите до четверга, если сможете прийти."],
  ["cake-confirmation", "2026-05-09", "Торт на день рождения готовят к субботе", "Заказали лимонный торт на десять гостей. Забрать можно после 14:00."],
  ["vet-appointment", "2026-05-11", "Запись кота Тимы к ветеринару", "Приём назначен на 13 мая на 12:00. Возьмите ветеринарный паспорт."],
  ["vet-reminder", "2026-05-14", "Памятка после вакцинации кота Тимы", "Следующая плановая вакцинация через год. Отметка о прививке есть в ветеринарном паспорте."],
  ["shoe-repair", "2026-05-22", "Обувь из мастерской можно забрать", "Поменяли набойки и восстановили подошву. Мастерская открыта до 20:00."],
  ["bicycle-service", "2026-06-03", "Велосипед готов после обслуживания", "Почистили трансмиссию и отрегулировали тормоза. Можно забрать в любой день до воскресенья."],
  ["bicycle-route", "2026-06-05", "Велопрогулка по набережной", "Старт у моста в 10:00. Круг около 18 км, по пути остановимся на кофе."],
  ["photo-delivery", "2026-06-06", "Фотографии с выпускного готовы", "Галерея доступна до 30 июня. Выберите три кадра для печати и ответьте на это письмо."]
].map(([doc_id, day, subject, body]) => ({ doc_id, day, subject, preview: body, body }));

let boxes = {};
let submitted = "";
let searchVersion = 0;
let messageVersion = 0;
let activeRow = null;
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

function action(label, handler, container = actions) {
  const button = node("button", label, "link");
  button.type = "button";
  button.addEventListener("click", handler);
  container.append(button);
  return button;
}

function relative(delta) {
  if (delta === 0) return "В тот же день";
  const count = Math.abs(delta);
  const unit = new Intl.PluralRules("ru").select(count) === "few" ? "дня" : "дней";
  const amount = count === 1 ? "день" : count + " " + unit;
  return delta < 0 ? "За " + amount + " до" : "Через " + amount;
}

function renderRows(items, select, container = rows) {
  for (const item of items) {
    const row = node("button", "", "row");
    row.type = "button";
    row.append(node("strong", item.subject || "Без темы"),
      node("small", displayDate(item.day), "meta"), node("span", item.preview || ""));
    if (Number.isInteger(item.delta_days)) row.append(node("small", relative(item.delta_days), "relative"));
    row.addEventListener("click", () => select(item, row));
    if (item.isAnchor) row.append(node("small", "Письмо-ориентир", "relative"));
    container.append(row);
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
    heading.textContent = data.length ? (text ? "Результаты поиска" : "Последние письма") :
      (text ? "По запросу «" + text + "» писем не найдено" : "Писем пока нет");
    renderRows(data, (item, row) => openMessage(context, item, row));
    const day = headers?.get("X-Target-Day");
    const fallback = headers?.get("X-Search-Mode") === "bm25-fallback";
    status.textContent = "Писем: " + data.length + (day ? " · За " + displayDate(day) : "") +
      (fallback ? " · Поиск по словам" : "");
    syncRecallVisibility();
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

function resetDate() {
  const today = new Date();
  const localDate = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  asOf.value = boxes[mailbox.value] || localDate;
}

async function loadSource() {
  resetRecall();
  const version = start("Загружаем ящики…");
  const demo = source.value === "demo";
  mailbox.replaceChildren();
  asOf.value = "";
  get("submit").disabled = true;
  syncRecallVisibility();
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
  runSearch(true);
});
mailbox.addEventListener("change", () => { resetDate(); runSearch(); });
asOf.addEventListener("change", () => runSearch());
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

const recallSlot = get("recall-slot");
const recallInput = get("recall-input");
const recallToggle = get("recall-toggle");
const notice = get("recall-status");
const recovery = get("recall-recovery");
const candidates = get("recall-candidates");
const dateForm = get("date-form");
const periodEditor = get("period-editor");
const preview = get("period-preview");
const fromField = get("period-from");
const toField = get("period-to");
const timeline = get("timeline");
const timelineRows = get("timeline-rows");
const timelineNav = get("timeline-nav");

let recallContext;
let recallVersion = 0;
let period;
let suggestion;
let timelineOrigin;
let timelinePosition;

let standaloneRecall = false;

function syncRecallVisibility() {
  const hasQuery = Boolean(query.value.trim());
  const visible = timeline.hidden && (hasQuery || standaloneRecall);
  recallSlot.inert = !visible;
  recallSlot.toggleAttribute("data-visible", visible);
  get("recall-entry").hidden = hasQuery || get("submit").disabled || !asOf.value;
  recallToggle.setAttribute("aria-expanded", String(visible && !hasQuery));
}

function openRecall(focus = true) {
  standaloneRecall = !query.value.trim();
  syncRecallVisibility();
  if (focus) recallInput.focus();
}

function clearRecallFields() {
  ++recallVersion;
  period = suggestion = null;
  fromField.value = toField.value = "";
  notice.textContent = "";
  recovery.replaceChildren();
  candidates.replaceChildren();
  candidates.hidden = dateForm.hidden = periodEditor.hidden = preview.hidden = true;
}

function resetRecall(keepHint = false) {
  clearRecallFields();
  recallContext = timelineOrigin = null;
  standaloneRecall = false;
  timeline.hidden = true;
  get("list").hidden = false;
  if (!keepHint) recallInput.value = "";
  syncRecallVisibility();
}

function mailContext(text) {
  if (!mailbox.value || !asOf.value || get("submit").disabled) return null;
  return { scope: { mailbox: mailbox.value, as_of: asOf.value }, text, demo: source.value === "demo" };
}

function runSearch(keepHint = false) {
  resetRecall(keepHint);
  const context = mailContext(submitted);
  if (!context) return start("Выберите дату отсчёта");
  ordinary(context, submitted);
}

function eventRequest(operation, payload, context = recallContext) {
  return request("/api/event-recall/" + operation, {}, { ...context.scope, ...payload }).then(response => response.data);
}

async function recallOperation(operation, work, render, retry, output = notice, buttons = recovery) {
  const version = ++recallVersion;
  const context = recallContext;
  output.textContent = operation;
  buttons.replaceChildren();
  try {
    const data = await work();
    if (version !== recallVersion) return;
    output.textContent = "";
    render(data);
  } catch (error) {
    if (version !== recallVersion) return;
    output.textContent = describeError(error);
    action("Повторить", retry, buttons);
    if (!context.demo) {
      if (error.status === 404 || error.status === 405 || error.status === 501) {
        output.textContent = "Почтовому API пока нужна операция «Вспомнить по событию».";
      }
      action("Открыть демоданные", () => {
        const hint = recallInput.value;
        source.value = "demo";
        loadSource().then(() => {
          if (source.value !== "demo" || !mailContext(query.value.trim())) return;
          recallInput.value = hint;
          openRecall();
        });
      }, buttons);
    }
  }
}

const months = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(" ");

function validDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(dayNumber(value)) &&
    dateString(dayNumber(value)) === value;
}

function demoSuggest(text, asOfDate) {
  const relation = text.match(/^(?:это было\s+)?\s*(до|после)\s+/iu);
  const direction = relation ? { до: "before", после: "after" }[relation[1].toLowerCase()] : "around";
  const term = text.replace(/^(?:это было\s+)?\s*(?:до|после|примерно тогда(?: же)?(?:,? когда)?|примерно в то же время(?:,? когда)?)\s+/iu, "")
    .replace(/^(?:я\s+|письма\s+(?:про|о|об)\s+)/iu, "").trim();
  const relativeDates = { сегодня: 0, вчера: 1, позавчера: 2 };
  const offset = relativeDates[term.toLowerCase()];
  const iso = Number.isInteger(offset) ? [term, dateString(dayNumber(asOfDate) - offset)] :
    term.match(/^(\d{4}-\d{2}-\d{2})(?:\s*[-–—]\s*(\d{4}-\d{2}-\d{2}))?$/);
  const named = term.match(/^(?:с\s+)?(\d{1,2})(?:(?:\s*[-–—]\s*|\s+по\s+)(\d{1,2}))?\s+([а-яё]+)(?:\s+(\d{4}))?$/iu);
  if (iso || named) {
    const year = named?.[4] || asOfDate.slice(0, 4);
    const month = String(months.indexOf(named?.[3]?.toLowerCase()) + 1).padStart(2, "0");
    const from = iso?.[1] || year + "-" + month + "-" + named[1].padStart(2, "0");
    const to = iso?.[2] || (named?.[2] ? year + "-" + month + "-" + named[2].padStart(2, "0") : from);
    if (!validDate(from) || !validDate(to) || from > to) {
      return { kind: "clarify", message: "Проверьте даты и укажите начало и конец периода." };
    }
    const range = from !== to;
    if (direction === "after") return { kind: "period", from: dateString(dayNumber(to) + Number(range)), to: dateString(dayNumber(to) + 3) };
    if (direction === "before") return { kind: "period", from: dateString(dayNumber(from) - 3), to: dateString(dayNumber(from) - Number(range)) };
    if (!range && /^примерно/iu.test(text)) {
      return { kind: "period", from: dateString(dayNumber(from) - 3), to: dateString(dayNumber(to) + 3) };
    }
    return { kind: "period", from, to };
  }
  if (/праздник|прошл(?:ой|ую) недел|конец месяц/iu.test(term)) {
    return { kind: "clarify", message: direction === "after" ? "После какой даты?" :
      direction === "before" ? "До какой даты?" : "Какой период вы помните?" };
  }
  const matches = term.length < 3 ? [] : demoMatches(term, demoMail.filter(item => item.day <= asOfDate))
    .sort((a, b) => b.score - a.score).slice(0, 3).map(row => row.item);
  return { kind: "anchors", direction, candidates: matches };
}

function showDates() {
  dateForm.hidden = false;
  fromField.value = period?.from || fromField.value;
  toField.value = period?.to || toField.value;
  fromField.max = toField.max = recallContext.scope.as_of;
  fromField.focus();
}

function resolveHint() {
  const text = recallInput.value.trim();
  const context = mailContext(query.value.trim());
  if (!text || !context) return;
  recallContext = context;
  const { scope, demo } = context;
  period = suggestion = null;
  candidates.hidden = dateForm.hidden = preview.hidden = periodEditor.hidden = true;
  recallOperation("Подбираем период…", () => demo ? demoSuggest(text, scope.as_of) : eventRequest("suggest", { text }), data => {
    if (data.kind === "period") confirmPeriod({ from: data.from, to: data.to });
    else if (data.kind === "clarify") {
      notice.textContent = data.message;
      showDates();
    } else {
      suggestion = data;
      showCandidates();
    }
  }, resolveHint);
}

function showCandidates() {
  candidates.replaceChildren();
  candidates.hidden = !suggestion.candidates.length;
  notice.textContent = candidates.hidden ? "Попробуйте описать событие иначе или укажите даты." : {
    before: "До какого письма искать?",
    after: "После какого письма искать?",
    around: "Какое письмо поможет вспомнить дату?"
  }[suggestion.direction];
  renderRows(suggestion.candidates, anchor => confirmPeriod({ anchor, direction: suggestion.direction, size: 3 }), candidates);
}

function localPeriod(selection, asOfDate) {
  let { from, to } = selection;
  if (selection.anchor) {
    const { anchor, direction, size } = selection;
    const day = dayNumber(anchor.day);
    from = dateString(day - (direction === "after" ? 0 : size));
    to = dateString(day + (direction === "before" ? 0 : size));
  }
  to = to < asOfDate ? to : asOfDate;
  if (!validDate(from) || !validDate(to) || from > to) throw new Error("Укажите доступный период до даты отсчёта.");
  return { from, to };
}

function periodPayload(selection) {
  return selection.anchor ? {
    anchor_doc_id: selection.anchor.doc_id, direction: selection.direction, window_days: selection.size
  } : { from: selection.from, to: selection.to };
}

function periodLabel(selection) {
  const dates = displayDate(selection.from) + " — " + displayDate(selection.to);
  if (!selection.anchor) return dates;
  const phrase = { before: "до письма", after: "после письма", around: "примерно тогда же, когда пришло письмо" };
  return dates + " · " + phrase[selection.direction] + " «" + (selection.anchor.subject || "Без темы") + "»";
}

function confirmPeriod(selection, after) {
  const context = recallContext;
  preview.hidden = true;
  recallOperation("Проверяем даты…", () => context.demo ? localPeriod(selection, context.scope.as_of) :
    eventRequest("period", periodPayload(selection), context), window => {
    period = { ...selection, ...window };
    candidates.hidden = dateForm.hidden = periodEditor.hidden = true;
    preview.hidden = false;
    get("period-summary").textContent = periodLabel(period);
    get("period-direction").value = period.direction || "around";
    get("refine").hidden = !context.text;
    get("timeline-open").textContent = context.text ? "Посмотреть письма вокруг события" : "Показать письма за этот период";
    get("timeline-open").className = context.text ? "link" : "primary";
    if (after) after(period);
    else (context.text ? get("refine") : get("timeline-open")).focus({ preventScroll: true });
  }, () => confirmPeriod(selection, after));
}

function matchingPeriod(context, selected) {
  const anchorDay = selected.anchor ? dayNumber(selected.anchor.day) : null;
  const eligible = demoMail.filter(item => item.day >= selected.from && item.day <= selected.to &&
    item.doc_id !== selected.anchor?.doc_id);
  return demoMatches(context.text, eligible).map(({ item, score }) => ({
    item: anchorDay === null ? item : { ...item, delta_days: dayNumber(item.day) - anchorDay }, score
  })).sort((a, b) => b.score - a.score ||
    Math.abs(a.item.delta_days ?? 0) - Math.abs(b.item.delta_days ?? 0) ||
    a.item.doc_id.localeCompare(b.item.doc_id)).slice(0, 10).map(entry => entry.item);
}

function refine(selected = period) {
  const context = recallContext;
  const retry = () => refine(selected);
  recallOperation("Ищем письма в выбранном периоде…", () => context.demo ?
    { results: matchingPeriod(context, selected) } :
    eventRequest("search", { ...periodPayload(selected), q: context.text, limit: 10 }, context), data => {
    submitted = context.text;
    preview.hidden = true;
    start(data.results.length ? "Результаты за выбранный период" : "За этот период писем не найдено");
    condition.textContent = context.text + " · " + periodLabel({ ...selected, ...data.window });
    condition.hidden = false;
    renderRows(data.results, (item, row) => openMessage(context, item, row));
    status.textContent = "Писем: " + data.results.length;
    action("Снять период", () => {
      ++recallVersion;
      ordinary(context, context.text).then(() => heading.focus());
    });
    if (!data.results.length) {
      if (selected.size === 3) action("Расширить до 7 дней", () => {
        openRecall();
        confirmPeriod({ ...selected, size: 7 }, refine);
      });
      action("Изменить период", () => { openRecall(false); showDates(); });
    }
    action("Посмотреть письма вокруг события", () => openTimeline(selected));
    heading.focus();
  }, retry);
}

const timelineNotice = get("timeline-status");
const timelineRecovery = get("timeline-recovery");
const pageSize = 12;
let lastDay;

function openTimeline(selected) {
  timelineOrigin = {
    status: status.textContent, activeRow, scroll: rows.scrollTop,
    message: [...message.childNodes], reading: reader.classList.contains("reading"),
    trigger: document.activeElement
  };
  get("list").hidden = true;
  timeline.hidden = false;
  syncRecallVisibility();
  loadTimeline({ from: selected.from, to: selected.to, anchor: selected.anchor });
}

function readTimeline(context, selection, cursor) {
  const anchorId = selection.anchor?.doc_id;
  if (!context.demo) return eventRequest("timeline", {
    from: selection.from, to: selection.to, anchor_doc_id: anchorId, cursor, limit: pageSize
  }, context);
  const eligible = demoMail.filter(item => item.day >= selection.from && item.day <= selection.to)
    .sort((a, b) => a.day.localeCompare(b.day) || a.doc_id.localeCompare(b.doc_id));
  const offset = cursor || 0;
  const end = offset + pageSize;
  return { results: eligible.slice(offset, end), next_cursor: end < eligible.length ? end : null };
}

function loadTimeline(selection, cursor = null) {
  const context = recallContext;
  timelinePosition = selection;
  if (cursor === null) {
    closeMessage();
    activeRow = null;
    lastDay = null;
    timelineRows.replaceChildren();
    timelineNav.replaceChildren();
    timelineRows.scrollTop = 0;
    get("timeline-period").textContent = displayDate(selection.from) + " — " + displayDate(selection.to) +
      (selection.anchor ? " · «" + (selection.anchor.subject || "Без темы") + "»" : "");
    get("timeline-title").focus({ preventScroll: true });
  } else timelineNav.querySelectorAll("button").forEach(button => { button.disabled = true; });

  recallOperation("Загружаем письма за этот период…", () => readTimeline(context, selection, cursor), data => {
    for (const item of data.results) {
      if (item.day !== lastDay) {
        timelineRows.append(node("h3", displayDate(item.day), "timeline-day"));
        lastDay = item.day;
      }
      renderRows([{ ...item, isAnchor: item.doc_id === selection.anchor?.doc_id }],
        (mail, row) => openMessage(context, mail, row), timelineRows);
    }
    if (cursor === null && !data.results.length) timelineNotice.textContent = "За этот период писем нет.";
    renderTimelineNav(data.next_cursor);
  }, () => loadTimeline(selection, cursor), timelineNotice, timelineRecovery);
}

function renderTimelineNav(nextCursor) {
  const { from, to, anchor } = timelinePosition;
  const first = dayNumber(from);
  const last = dayNumber(to);
  const cutoff = dayNumber(recallContext.scope.as_of);
  timelineNav.replaceChildren();
  action("Предыдущие 7 дней", () => loadTimeline({
    from: dateString(first - 7), to: dateString(first - 1), anchor
  }), timelineNav);
  const next = action("Следующие 7 дней", () => loadTimeline({
    from: dateString(last + 1), to: dateString(Math.min(last + 7, cutoff)), anchor
  }), timelineNav);
  next.disabled = last >= cutoff;
  if (nextCursor != null) action("Показать ещё", () => loadTimeline(timelinePosition, nextCursor), timelineNav);
}

function closeTimeline() {
  ++recallVersion;
  ++messageVersion;
  const previous = timelineOrigin;
  timelineOrigin = null;
  timeline.hidden = true;
  get("list").hidden = false;
  syncRecallVisibility();
  status.textContent = previous.status;
  activeRow = previous.activeRow;
  message.replaceChildren(...previous.message);
  reader.classList.toggle("reading", previous.reading);
  rows.scrollTop = previous.scroll;
  const trigger = previous.trigger;
  (previous.reading ? message.querySelector("h2") :
    trigger && document.contains(trigger) ? trigger : query)?.focus({ preventScroll: true });
}

query.addEventListener("input", () => {
  if (timeline.hidden) clearRecallFields();
  standaloneRecall = false;
  syncRecallVisibility();
});
recallToggle.addEventListener("click", () => {
  if (standaloneRecall) {
    standaloneRecall = false;
    syncRecallVisibility();
  } else {
    openRecall();
  }
});
get("recall-form").addEventListener("submit", event => {
  event.preventDefault();
  resolveHint();
});
get("recall-dates").addEventListener("click", () => {
  const context = mailContext(query.value.trim());
  if (!context) return;
  recallContext = context;
  ++recallVersion;
  notice.textContent = "";
  recovery.replaceChildren();
  showDates();
});
dateForm.addEventListener("submit", event => {
  event.preventDefault();
  confirmPeriod({ from: fromField.value, to: toField.value });
});
get("period-edit").addEventListener("click", () => {
  periodEditor.hidden = !period.anchor;
  showDates();
});
get("period-direction").addEventListener("change", event => confirmPeriod({ ...period, direction: event.target.value }));
get("recall-change-anchor").addEventListener("click", () => {
  preview.hidden = dateForm.hidden = periodEditor.hidden = true;
  showCandidates();
  (candidates.querySelector("button") || recallInput).focus();
});
get("refine").addEventListener("click", () => refine());
get("timeline-open").addEventListener("click", () => openTimeline(period));
get("timeline-back").addEventListener("click", closeTimeline);

if (new URLSearchParams(location.search).get("demo") === "1") source.value = "demo";
loadSource();
