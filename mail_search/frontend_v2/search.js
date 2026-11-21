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
const suggestions = get("suggestions");
const suggestionOptions = get("suggestion-options");
const help = "Для поиска по ориентиру бэкенду нужны GET /api/search с dated_only=true и POST /api/search/nearby.";
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
  ["team-demo", "2026-04-17", "Демонстрация новой отчётности", "На пятничном созвоне покажем отчёт по обращениям и обсудим метрики поддержки."],
  ["team-notes", "2026-04-18", "Протокол обсуждения отчётности", "Согласовали сверку за апрель. Полина проверит выгрузку, Илья обновит отчёт к 24 апреля."],
  ["stand-access", "2026-04-02", "Доступ к тестовому стенду открыт", "У вашей команды есть доступ на чтение к журналу сборок. Для входа используйте рабочую учётную запись."],
  ["vendor-invoice", "2026-04-04", "Счёт за обслуживание тестового стенда", "Сумма за апрель — 8 900 ₽. Просьба указать номер счёта в назначении платежа."],
  ["office-pass", "2026-05-21", "Гостевой пропуск в офис на четверг", "Покажите паспорт на стойке регистрации. Пропуск действует до 19:00."],

  ["lease-draft", "2026-03-28", "Проект договора аренды квартиры", "Проверьте срок аренды и пункт о залоге. В договор включена мебель из описи."],
  ["lease-viewing", "2026-03-30", "Просмотр квартиры на Парковой", "Встречаемся у второго подъезда в 18:30. Домофон откроет менеджер."],
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
let activeSuggestion = -1;
let completion = "";

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

function hideSuggestions() {
  suggestions.hidden = true;
  activeSuggestion = -1;
  query.setAttribute("aria-expanded", "false");
  query.removeAttribute("aria-activedescendant");
}

function applySuggestion(value) {
  query.value = completion = value;
  hideSuggestions();
  query.focus();
}

function suggest() {
  hideSuggestions();
  const text = query.value.trim();
  if (text.length < 2 || parse(text) || text === completion.trim()) return;

  const list = /^письма(?:\s+рядом(?:\s+с)?)?$/iu.test(text) ? [
    ["Письма рядом с ", "Например, с покупкой билетов в Казань"]
  ] : [
    [text + " после письма про ", "Например, про билеты в Казань"],
    [text + " до письма про ", "Например, про приглашение на встречу"],
    [text + " примерно тогда, когда ", "Например, когда пришло подтверждение брони"]
  ];
  suggestionOptions.replaceChildren();
  for (const [value, example] of list) {
    if (value.length >= query.maxLength) continue;
    const option = node("li", "");
    option.id = "suggestion-" + suggestionOptions.children.length;
    option.setAttribute("role", "option");
    option.setAttribute("aria-selected", "false");
    option.append(node("strong", value + "…"), node("small", example, "meta"));
    option.addEventListener("pointerdown", event => event.preventDefault());
    option.addEventListener("click", () => applySuggestion(value));
    suggestionOptions.append(option);
  }
  if (!suggestionOptions.children.length) return;
  suggestions.hidden = false;
  query.setAttribute("aria-expanded", "true");
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
  hideSuggestions();
  if (completion && query.value.trim() === completion.trim()) {
    status.textContent = "Допишите, какое письмо или событие вы помните.";
    query.focus();
    return;
  }
  submitted = query.value.trim();
  runSearch();
});
query.addEventListener("input", event => {
  if (!event.isComposing) suggest();
});
query.addEventListener("compositionend", suggest);
query.addEventListener("blur", hideSuggestions);
query.addEventListener("keydown", event => {
  if (suggestions.hidden || event.isComposing) return;
  const options = [...suggestionOptions.children];
  if (event.key === "Escape") {
    event.preventDefault();
    hideSuggestions();
  } else if (event.key === "Enter" && activeSuggestion >= 0) {
    event.preventDefault();
    options[activeSuggestion].click();
  } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    options[activeSuggestion]?.setAttribute("aria-selected", "false");
    const step = event.key === "ArrowDown" ? 1 : -1;
    activeSuggestion = activeSuggestion < 0 ? (step === 1 ? 0 : options.length - 1) :
      (activeSuggestion + step + options.length) % options.length;
    const selected = options[activeSuggestion];
    selected.setAttribute("aria-selected", "true");
    query.setAttribute("aria-activedescendant", selected.id);
  }
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
if (new URLSearchParams(location.search).get("demo") === "1") source.value = "demo";
loadSource();
