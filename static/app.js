const state = {
  article: null,
  index: 0,
  sentenceMarks: new Map(),
  sentenceMarkOrder: new Map(),
  nextSentenceMarkOrder: 0,
  alwaysRecognized: new Set(),
  sessionCounts: new Map(),
  globalCounts: new Map(),
  viewedSentenceIds: new Set(),
  tokenCatalog: new Map(),
  activeToken: null,
  sessionId: null,
  summarySort: "recognized",
  summary: null,
  sessionHistory: [],
  sessionHistoryDetail: null,
  sessionHistorySort: "recognized",
  sentenceAidCache: new Map(),
  revealedSentenceAids: new Set(),
};

const ACTIVE_SESSION_STORAGE_PREFIX = "japaneseReaderActiveSession:v1:";

const articleTitle = document.querySelector("#article-title");
const landing = document.querySelector("#landing");
const reader = document.querySelector("#reader");
const sessionFooter = document.querySelector("#session-footer");
const articleForm = document.querySelector("#article-form");
const articleUrl = document.querySelector("#article-url");
const formStatus = document.querySelector("#form-status");
const loadingBar = document.querySelector("#loading-bar");
const sentenceIndex = document.querySelector("#sentence-index");
const sentenceEl = document.querySelector("#sentence");
const sentenceAids = document.querySelector("#sentence-aids");
const sentenceRomaji = document.querySelector("#sentence-romaji");
const sentenceEnglish = document.querySelector("#sentence-english");
const revealSentenceAidsButton = document.querySelector("#reveal-sentence-aids");
const previousButton = document.querySelector("#previous");
const nextButton = document.querySelector("#next");
const logSessionButton = document.querySelector("#log-session");
const endSessionButton = document.querySelector("#end-session");
const checkpointStatus = document.querySelector("#checkpoint-status");
const themeLightButton = document.querySelector("#theme-light");
const themeDarkButton = document.querySelector("#theme-dark");
const popover = document.querySelector("#popover");
const popoverSurface = document.querySelector("#popover-surface");
const popoverToken = document.querySelector("#popover-token");
const popoverReading = document.querySelector("#popover-reading");
const popoverTranslation = document.querySelector("#popover-translation");
const popoverPlaces = document.querySelector("#popover-places");
const popoverPhrases = document.querySelector("#popover-phrases");
const popoverInherited = document.querySelector("#popover-inherited");
const previewCardButton = document.querySelector("#preview-card");
const cardPreview = document.querySelector("#card-preview");
const cardPreviewExpression = document.querySelector("#card-preview-expression");
const cardPreviewReading = document.querySelector("#card-preview-reading");
const cardPreviewRomaji = document.querySelector("#card-preview-romaji");
const cardPreviewMeaning = document.querySelector("#card-preview-meaning");
const cardPreviewSurface = document.querySelector("#card-preview-surface");
const cardPreviewSentence = document.querySelector("#card-preview-sentence");
const cardPreviewSentenceRomaji = document.querySelector("#card-preview-sentence-romaji");
const cardPreviewSentenceTranslation = document.querySelector("#card-preview-sentence-translation");
const cardPreviewSource = document.querySelector("#card-preview-source");
const cardPreviewDictionary = document.querySelector("#card-preview-dictionary");
const cardPreviewAnswer = document.querySelector("#card-preview-answer");
const confirmOverlay = document.querySelector("#confirm");
const cancelEndButton = document.querySelector("#cancel-end");
const confirmEndButton = document.querySelector("#confirm-end");
const sessionSummaryList = document.querySelector("#session-summary-list");
const ankiSyncStatus = document.querySelector("#anki-sync-status");
const summaryDialog = document.querySelector("#summary-dialog");
const studyLogDialog = document.querySelector("#study-log-dialog");
const studyLogIndex = document.querySelector("#study-log-index");
const studyLogDetail = document.querySelector("#study-log-detail");
let activeAnchor = null;

setTheme(localStorage.getItem("wikiReaderTheme") === "dark" ? "dark" : "light");

const initialArticle = new URLSearchParams(window.location.search).get("article");
if (initialArticle) {
  articleUrl.value = initialArticle;
  void loadArticle(initialArticle);
}

articleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await loadArticle(articleUrl.value);
});
previousButton.addEventListener("click", () => navigate(-1));
nextButton.addEventListener("click", () => navigate(1));
revealSentenceAidsButton.addEventListener("click", () => {
  void revealSentenceAids(currentSentence());
});
themeLightButton.addEventListener("click", () => setTheme("light"));
themeDarkButton.addEventListener("click", () => setTheme("dark"));
document.querySelector("#summary-button").addEventListener("click", openSummary);
document.querySelector("#study-log-button").addEventListener("click", openStudyLog);
document.querySelector("#summary-close").addEventListener("click", () => {
  summaryDialog.close();
});
document.querySelector("#study-log-close").addEventListener("click", () => {
  studyLogDialog.close();
});
document.querySelector("#study-log-back").addEventListener("click", showStudyLogIndex);
document.querySelectorAll("[data-summary-sort]").forEach((button) => {
  button.addEventListener("click", () => {
    state.summarySort = button.dataset.summarySort;
    renderVocabularySummary();
  });
});
document.querySelectorAll("[data-history-sort]").forEach((button) => {
  button.addEventListener("click", () => {
    state.sessionHistorySort = button.dataset.historySort;
    renderStudyLogDetail();
  });
});
logSessionButton.addEventListener("click", async () => {
  hidePopover();
  logSessionButton.disabled = true;
  endSessionButton.disabled = true;
  checkpointStatus.textContent = "Logging new and changed cards…";
  try {
    await persistEncounteredPlaces();
    const syncResult = await syncAnkiSession({ checkpoint: true });
    checkpointStatus.textContent = ankiSyncResultLabel(syncResult);
  } catch (error) {
    checkpointStatus.textContent = error.message;
    window.alert(error.message);
  } finally {
    logSessionButton.disabled = false;
    endSessionButton.disabled = false;
  }
});
endSessionButton.addEventListener("click", () => {
  hidePopover();
  renderSessionSummary();
  confirmOverlay.hidden = false;
  void refreshAnkiStatus();
});
cancelEndButton.addEventListener("click", () => {
  confirmOverlay.hidden = true;
});
confirmEndButton.addEventListener("click", async () => {
  confirmEndButton.disabled = true;
  try {
    await persistEncounteredPlaces();
    const syncResult = await syncAnkiSession();
    for (const row of sessionSummaryRows()) {
      const canonical = row.canonical;
      const global = state.globalCounts.get(canonical) ?? {
        encounters: 0,
        recognitions: 0,
      };
      global.encounters += row.encounters;
      global.recognitions += row.recognitions;
      state.globalCounts.set(canonical, global);
    }
    ankiSyncStatus.textContent = ankiSyncResultLabel(syncResult);
    confirmOverlay.hidden = true;
    clearActiveSession();
    resetToLanding();
  } catch (error) {
    window.alert(error.message);
  } finally {
    confirmEndButton.disabled = false;
  }
});

popover.addEventListener("click", (event) => {
  if (event.target.closest("#preview-card")) {
    toggleCardPreview();
    return;
  }
  const button = event.target.closest("[data-choice]");
  if (!button || !state.activeToken) return;
  void chooseToken(state.activeToken, button.dataset.choice).catch((error) => {
    window.alert(error.message);
  });
});

document.addEventListener("click", (event) => {
  if (event.target.closest(".token") || event.target.closest("#popover")) return;
  hidePopover();
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || popover.hidden) return;
  event.preventDefault();
  const anchor = activeAnchor;
  hidePopover();
  anchor?.focus();
});

async function loadArticle(value) {
  setLoading(true, "Starting article load…", 0);
  try {
    const startResponse = await fetch("/api/article-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: value }),
    });
    const startPayload = await startResponse.json();
    if (!startResponse.ok) {
      throw new Error(startPayload.error || "Could not start article load.");
    }
    if (startPayload.article) {
      await startSession(startPayload.article);
      return;
    }
    if (!startPayload.job_id) {
      throw new Error("Article load did not return a job.");
    }
    const article = await waitForArticleJob(startPayload.job_id);
    await startSession(article);
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    setLoading(false);
  }
}

async function waitForArticleJob(jobId) {
  while (true) {
    await delay(250);
    const response = await fetch(`/api/article-jobs/${jobId}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not check article loading progress.");
    }
    const total = Number(payload.total) || 0;
    const processed = Number(payload.processed) || 0;
    const progress = Number(payload.progress) || 0;
    const message = payload.message || (total > 0
      ? `Analyzing sentence ${processed} of ${total}...`
      : "Loading article...");
    setLoading(true, message, progress);
    if (payload.status === "complete") return payload.article;
    if (payload.status === "error") {
      throw new Error(payload.error || payload.message || "Could not load article.");
    }
  }
}

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function setLoading(isLoading, message = "", progress = 0) {
  formStatus.textContent = message;
  articleForm.querySelector("button").disabled = isLoading;
  articleUrl.disabled = isLoading;
  loadingBar.hidden = !isLoading;
  loadingBar.setAttribute("aria-valuenow", String(Math.round(progress * 100)));
  loadingBar.querySelector(".loading-fill").style.inlineSize = `${Math.max(
    0,
    Math.min(1, progress),
  ) * 100}%`;
}

async function openSummary() {
  try {
    const options = state.article
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: state.sessionId,
            cards: ankiSyncPlan().summaryCards,
            scope: "session",
          }),
        }
      : {};
    const response = await fetch("/api/summary", options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Could not load the vocabulary summary.");
    }
    state.summary = payload;
    renderVocabularySummary();
    if (!summaryDialog.open) summaryDialog.showModal();
  } catch (error) {
    window.alert(error.message);
  }
}

async function openStudyLog() {
  try {
    const response = await fetch("/api/session-history");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Could not load saved reading sessions.");
    }
    state.sessionHistory = payload.sessions || [];
    state.sessionHistoryDetail = null;
    renderStudyLogIndex();
    showStudyLogIndex();
    if (!studyLogDialog.open) studyLogDialog.showModal();
  } catch (error) {
    window.alert(error.message);
  }
}

function renderStudyLogIndex() {
  const meta = document.querySelector("#study-log-meta");
  const list = document.querySelector("#study-log-list");
  const sessions = state.sessionHistory;
  meta.textContent = `${sessions.length} saved reading session${sessions.length === 1 ? "" : "s"}`;
  list.replaceChildren();
  if (!sessions.length) {
    const empty = document.createElement("p");
    empty.className = "vocabulary-summary-empty";
    empty.textContent = "No reading sessions have been logged yet.";
    list.append(empty);
    return;
  }

  const byArticle = new Map();
  for (const session of sessions) {
    const title = session.article_title || "Untitled article";
    if (!byArticle.has(title)) byArticle.set(title, []);
    byArticle.get(title).push(session);
  }
  for (const [title, articleSessions] of byArticle) {
    const group = document.createElement("section");
    group.className = "study-log-group";
    const heading = document.createElement("div");
    heading.className = "study-log-group-heading";
    const articleTitle = document.createElement("h3");
    articleTitle.lang = "ja";
    articleTitle.textContent = title;
    const count = document.createElement("span");
    count.textContent = `${articleSessions.length} session${articleSessions.length === 1 ? "" : "s"}`;
    heading.append(articleTitle, count);
    const rows = document.createElement("div");
    rows.className = "study-log-group-rows";
    for (const session of articleSessions) rows.append(studyLogSessionRow(session));
    group.append(heading, rows);
    list.append(group);
  }
}

function studyLogSessionRow(session) {
  const button = document.createElement("button");
  button.className = "study-log-session";
  button.type = "button";
  button.addEventListener("click", () => openStudyLogSession(session.session_id));

  const primary = document.createElement("span");
  primary.className = "study-log-session-primary";
  const date = document.createElement("strong");
  date.textContent = formatSavedSessionDate(session.last_saved_at);
  const status = document.createElement("span");
  status.className = `study-log-status ${session.status}`;
  status.textContent = session.status === "completed" ? "Ended" : "Logged";
  primary.append(date, status);

  const counts = document.createElement("span");
  counts.className = "study-log-session-counts";
  counts.textContent = [
    `${session.token_count} tokens`,
    `${session.recognized_count} recognized`,
    `${session.unrecognized_count} unrecognized`,
    session.always_count ? `${session.always_count} always` : "",
  ].filter(Boolean).join(" · ");

  const arrow = document.createElement("span");
  arrow.className = "study-log-session-arrow";
  arrow.setAttribute("aria-hidden", "true");
  arrow.textContent = "→";
  button.append(primary, counts, arrow);
  return button;
}

async function openStudyLogSession(sessionId) {
  try {
    const response = await fetch(`/api/session-history/${encodeURIComponent(sessionId)}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Could not load that reading session.");
    }
    state.sessionHistoryDetail = payload;
    renderStudyLogDetail();
    studyLogIndex.hidden = true;
    studyLogDetail.hidden = false;
  } catch (error) {
    window.alert(error.message);
  }
}

function showStudyLogIndex() {
  document.querySelector("#study-log-heading").textContent = "Reading sessions";
  studyLogDetail.hidden = true;
  studyLogIndex.hidden = false;
}

function renderStudyLogDetail() {
  const detail = state.sessionHistoryDetail;
  if (!detail) return;
  document.querySelector("#study-log-heading").textContent = detail.article_title;
  document.querySelectorAll("[data-history-sort]").forEach((button) => {
    button.setAttribute(
      "aria-selected",
      String(button.dataset.historySort === state.sessionHistorySort),
    );
  });

  const meta = document.querySelector("#study-log-session-meta");
  const status = detail.status === "completed" ? "Ended session" : "Logged checkpoint";
  meta.textContent = [
    formatSavedSessionDate(detail.last_saved_at),
    status,
    `${detail.token_count} tracked tokens`,
    `${detail.recognized_count} recognized`,
    `${detail.unrecognized_count} unrecognized`,
    detail.always_count ? `${detail.always_count} always recognized` : "",
  ].filter(Boolean).join(" · ");

  const list = document.querySelector("#study-log-vocabulary");
  list.replaceChildren();
  const values = sortedVocabularyTokens(
    detail.summary.tokens,
    state.sessionHistorySort,
  );
  if (!values.length) {
    const empty = document.createElement("p");
    empty.className = "vocabulary-summary-empty";
    empty.textContent = "No vocabulary was tracked in this session.";
    list.append(empty);
    return;
  }
  for (const token of values) list.append(vocabularySummaryRow(token));
}

function formatSavedSessionDate(value) {
  const normalized = String(value || "").replace(" ", "T");
  const date = new Date(`${normalized}Z`);
  if (Number.isNaN(date.getTime())) return String(value || "Unknown date");
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function sortedVocabularyTokens(tokens, sort) {
  const values = [...tokens];
  const expressionOrder = (left, right) => (
    String(left.expression).localeCompare(String(right.expression), "ja")
  );
  values.sort((left, right) => {
    if (sort === "unrecognized") {
      return right.unrecognized_count - left.unrecognized_count
        || left.recognized_count - right.recognized_count
        || expressionOrder(left, right);
    }
    if (sort === "difference") {
      return right.difference - left.difference
        || right.recognized_count - left.recognized_count
        || left.unrecognized_count - right.unrecognized_count
        || expressionOrder(left, right);
    }
    return right.recognized_count - left.recognized_count
      || right.unrecognized_count - left.unrecognized_count
      || expressionOrder(left, right);
  });
  return values;
}

function renderVocabularySummary() {
  if (!state.summary) return;
  document.querySelectorAll("[data-summary-sort]").forEach((button) => {
    button.setAttribute(
      "aria-selected",
      String(button.dataset.summarySort === state.summarySort),
    );
  });
  const values = sortedVocabularyTokens(state.summary.tokens, state.summarySort);

  const meta = document.querySelector("#vocabulary-summary-meta");
  meta.textContent = `${state.summary.token_count} tracked token${state.summary.token_count === 1 ? "" : "s"} in this reading session`;
  const list = document.querySelector("#vocabulary-summary-list");
  list.replaceChildren();
  if (!values.length) {
    const empty = document.createElement("p");
    empty.className = "vocabulary-summary-empty";
    empty.textContent = "No vocabulary has been tracked yet.";
    list.append(empty);
    return;
  }
  for (const token of values) list.append(vocabularySummaryRow(token));
}

function vocabularySummaryRow(token) {
  const row = document.createElement("article");
  row.className = "vocabulary-summary-row";
  const word = document.createElement("div");
  word.className = "vocabulary-summary-word";
  const expression = document.createElement("strong");
  expression.lang = "ja";
  expression.textContent = token.expression;
  const detail = document.createElement("span");
  detail.textContent = [token.hiragana, token.romaji, token.translation]
    .filter(Boolean)
    .join(" · ");
  const articles = document.createElement("small");
  articles.textContent = token.sessions
    .map((session) => session.article_title)
    .join(" · ");
  word.append(expression, detail, articles);

  const counts = document.createElement("div");
  counts.className = "vocabulary-summary-counts";
  counts.append(
    vocabularySummaryCount(token.recognized_count, "recognized", "recognized"),
    vocabularySummaryCount(token.unrecognized_count, "unrecognized", "unrecognized"),
    vocabularySummaryCount(formatDifference(token.difference), "difference", "difference"),
  );
  if (token.always_recognized) {
    counts.append(vocabularySummaryCount("active", "always recognized", "always"));
  } else if (token.always_count) {
    counts.append(vocabularySummaryCount(token.always_count, "past always", "always"));
  }
  row.append(word, counts);
  return row;
}

function vocabularySummaryCount(value, label, className) {
  const item = document.createElement("span");
  item.className = `vocabulary-summary-count ${className}`;
  item.textContent = `${value} ${label}`;
  return item;
}

function formatDifference(value) {
  return value > 0 ? `+${value}` : String(value);
}

async function startSession(article) {
  state.article = article;
  state.index = 0;
  state.sentenceMarks = new Map();
  state.sentenceMarkOrder = new Map();
  state.nextSentenceMarkOrder = 0;
  state.alwaysRecognized = await loadAlwaysRecognized();
  state.sessionCounts = new Map();
  state.viewedSentenceIds = new Set();
  state.tokenCatalog = new Map();
  state.activeToken = null;
  state.sentenceAidCache = new Map();
  state.revealedSentenceAids = new Set();
  for (const sentence of article.sentences) {
    if (!sentence.sentence_aid) continue;
    state.sentenceAidCache.set(sentenceAidKey(sentence), {
      romaji: sentence.sentence_aid.romaji || "",
      english: sentence.sentence_aid.english || "",
    });
  }
  state.sessionId = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const restoredMarks = restoreActiveSession(article);
  articleTitle.textContent = article.title;
  landing.hidden = true;
  reader.hidden = false;
  sessionFooter.hidden = false;
  formStatus.textContent = "";
  checkpointStatus.textContent = restoredMarks > 0
    ? `Restored ${restoredMarks} marked token${restoredMarks === 1 ? "" : "s"} from this reading session.`
    : "";
  render();
}

function activeSessionStorageKey(article = state.article) {
  if (!article) return "";
  const identity = [
    article.canonicalurl || "",
    article.revision_id || "",
    article.title || "",
  ].join("\u0000");
  return `${ACTIVE_SESSION_STORAGE_PREFIX}${encodeURIComponent(identity)}`;
}

function persistActiveSession() {
  const key = activeSessionStorageKey();
  if (!key || !state.sessionId) return;
  const payload = {
    version: 1,
    sessionId: state.sessionId,
    index: state.index,
    sentenceMarks: [...state.sentenceMarks.entries()],
    sentenceMarkOrder: [...state.sentenceMarkOrder.entries()],
    nextSentenceMarkOrder: state.nextSentenceMarkOrder,
    viewedSentenceIds: [...state.viewedSentenceIds],
    revealedSentenceAids: [...state.revealedSentenceAids],
  };
  localStorage.setItem(key, JSON.stringify(payload));
}

function restoreActiveSession(article) {
  const key = activeSessionStorageKey(article);
  if (!key) return 0;
  let payload;
  try {
    payload = JSON.parse(localStorage.getItem(key) || "null");
  } catch {
    localStorage.removeItem(key);
    return 0;
  }
  if (!payload || payload.version !== 1) return 0;

  const validSentences = new Set(article.sentences.map((sentence) => sentence.id));
  const catalogByMark = new Map();
  for (const sentence of article.sentences) {
    for (const token of sentence.tokens) {
      for (const entry of affectedTokenEntries({
        ...token,
        sentenceId: sentence.id,
        sentenceText: sentence.display_text,
      })) {
        catalogByMark.set(markKey(sentence.id, entry.canonical), entry);
      }
    }
  }

  const savedOrders = new Map(Array.isArray(payload.sentenceMarkOrder)
    ? payload.sentenceMarkOrder
    : []);
  const marks = Array.isArray(payload.sentenceMarks) ? payload.sentenceMarks : [];
  for (const pair of marks) {
    if (!Array.isArray(pair) || pair.length !== 2) continue;
    const [keyValue, choice] = pair;
    if (choice !== "recognized" && choice !== "unrecognized") continue;
    const entry = catalogByMark.get(String(keyValue));
    if (!entry) continue;
    state.sentenceMarks.set(String(keyValue), choice);
    const savedOrder = Number(savedOrders.get(String(keyValue)));
    if (Number.isFinite(savedOrder) && savedOrder > 0) {
      state.sentenceMarkOrder.set(String(keyValue), savedOrder);
    }
    registerTokenCatalog(entry);
    increment(entry.canonical, choice);
  }

  state.nextSentenceMarkOrder = Math.max(
    Number(payload.nextSentenceMarkOrder) || 0,
    ...state.sentenceMarkOrder.values(),
  );
  state.viewedSentenceIds = new Set(
    (Array.isArray(payload.viewedSentenceIds) ? payload.viewedSentenceIds : [])
      .filter((sentenceId) => validSentences.has(sentenceId)),
  );
  state.revealedSentenceAids = new Set(
    Array.isArray(payload.revealedSentenceAids)
      ? payload.revealedSentenceAids.map(String)
      : [],
  );
  const savedIndex = Number(payload.index);
  if (Number.isFinite(savedIndex)) {
    state.index = Math.max(0, Math.min(article.sentences.length - 1, Math.trunc(savedIndex)));
  }
  if (typeof payload.sessionId === "string" && payload.sessionId.length >= 8) {
    state.sessionId = payload.sessionId;
  }
  return state.sentenceMarks.size;
}

function clearActiveSession(article = state.article) {
  const key = activeSessionStorageKey(article);
  if (key) localStorage.removeItem(key);
}

async function loadAlwaysRecognized() {
  const response = await fetch("/api/always-recognized");
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "Could not load always-recognized vocabulary.");
  }
  return new Set(payload.token_ids || []);
}

function resetToLanding() {
  hidePopover();
  state.article = null;
  sessionSummaryList.replaceChildren();
  articleTitle.textContent = "Japanese Sentence Reader";
  landing.hidden = false;
  reader.hidden = true;
  sessionFooter.hidden = true;
}

function navigate(direction) {
  state.index = Math.max(
    0,
    Math.min(state.article.sentences.length - 1, state.index + direction),
  );
  hidePopover();
  render();
}

function render() {
  const sentence = currentSentence();
  markSentenceViewed(sentence);
  renderSentenceIndex();
  sentenceEl.replaceChildren(...renderSentence(sentence));
  renderSentenceAids(sentence);
  previousButton.disabled = state.index === 0;
  nextButton.disabled = state.index === state.article.sentences.length - 1;
  persistActiveSession();
}

function sentenceAidKey(sentence) {
  return `${state.article?.revision_id || "article"}:${sentence.id}`;
}

function renderSentenceAids(sentence) {
  const key = sentenceAidKey(sentence);
  const aid = state.sentenceAidCache.get(key);
  const revealed = state.revealedSentenceAids.has(key) && Boolean(aid);
  sentenceRomaji.textContent = aid?.romaji || "";
  sentenceEnglish.textContent = aid?.english || "";
  sentenceAids.classList.toggle("revealed", revealed);
  sentenceAids.classList.remove("error");
  revealSentenceAidsButton.disabled = false;
  revealSentenceAidsButton.textContent = "Reveal romaji + English";
  revealSentenceAidsButton.title = "";
  revealSentenceAidsButton.setAttribute("aria-expanded", String(revealed));
}

async function revealSentenceAids(sentence) {
  const key = sentenceAidKey(sentence);
  const existing = state.sentenceAidCache.get(key);
  if (existing) {
    state.revealedSentenceAids.add(key);
    renderSentenceAids(sentence);
    persistActiveSession();
    scrollSentenceAidsIntoView();
    return;
  }

  sentenceAids.classList.remove("error");
  revealSentenceAidsButton.disabled = true;
  revealSentenceAidsButton.textContent = "Generating reading aids…";
  try {
    const response = await fetch("/api/sentence-aid", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        japanese: sentence.display_text,
        previous: state.article.sentences[state.index - 1]?.display_text || "",
        following: state.article.sentences[state.index + 1]?.display_text || "",
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "Could not generate sentence reading aids.");
    }
    state.sentenceAidCache.set(key, {
      romaji: payload.romaji || "",
      english: payload.english || "",
    });
    state.revealedSentenceAids.add(key);
    persistActiveSession();
    if (sentenceAidKey(currentSentence()) === key) {
      renderSentenceAids(sentence);
      scrollSentenceAidsIntoView();
    }
  } catch (error) {
    if (sentenceAidKey(currentSentence()) !== key) return;
    sentenceAids.classList.add("error");
    revealSentenceAidsButton.disabled = false;
    revealSentenceAidsButton.textContent = "Reading aids unavailable — retry";
    revealSentenceAidsButton.title = error.message;
  }
}

function scrollSentenceAidsIntoView() {
  requestAnimationFrame(() => {
    sentenceAids.scrollIntoView({
      block: "nearest",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  });
}

function renderSentenceIndex() {
  const current = state.index + 1;
  const total = state.article.sentences.length;
  const jumpButton = document.createElement("button");
  jumpButton.className = "sentence-jump";
  jumpButton.type = "button";
  jumpButton.textContent = String(current);
  jumpButton.setAttribute("aria-label", `Jump from sentence ${current}`);
  jumpButton.addEventListener("click", showSentenceJumpInput);
  sentenceIndex.replaceChildren("Sentence ", jumpButton, ` of ${total}`);
}

function showSentenceJumpInput() {
  const total = state.article.sentences.length;
  const input = document.createElement("input");
  input.className = "sentence-jump-input";
  input.type = "number";
  input.min = "1";
  input.max = String(total);
  input.inputMode = "numeric";
  input.value = String(state.index + 1);
  input.setAttribute("aria-label", `Sentence number, 1 to ${total}`);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      commitSentenceJump(input.value);
    }
    if (event.key === "Escape") {
      renderSentenceIndex();
    }
  });
  input.addEventListener("blur", () => commitSentenceJump(input.value));
  sentenceIndex.replaceChildren("Sentence ", input, ` of ${total}`);
  input.focus();
  input.select();
}

function commitSentenceJump(value) {
  const total = state.article.sentences.length;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    renderSentenceIndex();
    return;
  }
  const sentenceNumber = Math.max(1, Math.min(total, Math.trunc(parsed)));
  state.index = sentenceNumber - 1;
  hidePopover();
  render();
}

function renderSentence(sentence) {
  const parts = [];
  let cursor = 0;
  const headingRanges = sentence.heading_ranges ?? [];
  for (const token of sentence.tokens) {
    const range = tokenDisplayRange(sentence, token, cursor);
    if (!range) continue;
    if (range.start > cursor) {
      appendTextSegment(parts, sentence.display_text, cursor, range.start, headingRanges);
    }
    const span = document.createElement("span");
    span.className = [
      "token",
      tokenClass(sentence.id, token.canonical),
      rangeOverlapsHeading(range.start, range.end, headingRanges)
        ? "heading-token"
        : "",
    ].filter(Boolean).join(" ");
    span.tabIndex = 0;
    span.setAttribute("role", "button");
    span.setAttribute("aria-haspopup", "dialog");
    span.setAttribute("aria-expanded", "false");
    span.textContent = sentence.display_text.slice(range.start, range.end);
    span.setAttribute("aria-label", `${span.textContent}: show token details`);
    span.addEventListener("click", (event) => showPopover(event.currentTarget, token, event));
    span.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      showPopover(event.currentTarget, token);
    });
    parts.push(span);
    cursor = range.end;
  }
  if (cursor < sentence.display_text.length) {
    appendTextSegment(
      parts,
      sentence.display_text,
      cursor,
      sentence.display_text.length,
      headingRanges,
    );
  }
  return parts;
}

function tokenDisplayRange(sentence, token, cursor) {
  const exactIndex = sentence.display_text.indexOf(token.surface, cursor);
  if (exactIndex >= 0) {
    return { start: exactIndex, end: exactIndex + token.surface.length };
  }
  if (!Number.isFinite(token.start) || !Number.isFinite(token.end)) return null;
  const start = analysisOffsetToDisplayOffset(token.start, sentence.suppressed_spans ?? []);
  const end = analysisOffsetToDisplayOffset(token.end, sentence.suppressed_spans ?? []);
  if (start < cursor || end <= start || end > sentence.display_text.length) return null;
  const displaySurface = sentence.display_text.slice(start, end);
  if (compactForMatch(displaySurface) !== compactForMatch(token.surface)) return null;
  return { start, end };
}

function analysisOffsetToDisplayOffset(offset, suppressedSpans) {
  let removed = 0;
  for (const span of suppressedSpans) {
    const start = Number(span.start);
    const end = Number(span.end);
    if (!Number.isFinite(start) || !Number.isFinite(end)) continue;
    const analysisStart = start - removed;
    if (offset >= analysisStart) {
      removed += end - start;
    }
  }
  return offset + removed;
}

function compactForMatch(value) {
  return String(value).replace(/\s+/g, "");
}

function appendTextSegment(parts, text, start, end, headingRanges) {
  let cursor = start;
  while (cursor < end) {
    const headingRange = headingRanges.find(
      (range) => cursor >= range.start && cursor < range.end,
    );
    const nextBoundary = nextHeadingBoundary(cursor, end, headingRanges);
    const value = text.slice(cursor, nextBoundary);
    if (headingRange) {
      const strong = document.createElement("strong");
      strong.className = "sentence-heading";
      strong.textContent = value;
      parts.push(strong);
    } else {
      parts.push(document.createTextNode(value));
    }
    cursor = nextBoundary;
  }
}

function nextHeadingBoundary(cursor, end, headingRanges) {
  for (const range of headingRanges) {
    if (cursor >= range.start && cursor < range.end) return Math.min(end, range.end);
    if (range.start > cursor) return Math.min(end, range.start);
  }
  return end;
}

function rangeOverlapsHeading(start, end, headingRanges) {
  return headingRanges.some((range) => start < range.end && end > range.start);
}

function tokenClass(sentenceId, canonical) {
  if (state.alwaysRecognized.has(canonical)) return "always";
  return sentenceMark(sentenceId, canonical) ?? "";
}

function sentenceMark(sentenceId, canonical) {
  return state.sentenceMarks.get(markKey(sentenceId, canonical));
}

function showPopover(anchor, token, event) {
  resetCardPreview();
  if (activeAnchor && activeAnchor !== anchor) {
    activeAnchor.classList.remove("active-token");
    activeAnchor.setAttribute("aria-expanded", "false");
  }
  activeAnchor = anchor;
  activeAnchor.classList.add("active-token");
  activeAnchor.setAttribute("aria-expanded", "true");
  state.activeToken = {
    ...token,
    sentenceId: currentSentence().id,
    sentenceText: currentSentence().display_text,
  };
  popoverSurface.textContent = token.surface;
  popoverToken.textContent = token.canonical;
  popoverReading.textContent = readingLabel(token);
  popoverTranslation.textContent = token.translation ? `meaning: ${token.translation}` : "";
  popoverPlaces.textContent = placeLabel(token);
  popoverPhrases.textContent = phraseLabel(token);
  popoverInherited.textContent = inheritedLabel(token);
  popover.hidden = false;
  positionPopover(anchor, event);
}

function hidePopover() {
  resetCardPreview();
  popover.hidden = true;
  activeAnchor?.classList.remove("active-token");
  activeAnchor?.setAttribute("aria-expanded", "false");
  activeAnchor = null;
  state.activeToken = null;
}

function resetCardPreview() {
  cardPreview.hidden = true;
  previewCardButton.setAttribute("aria-expanded", "false");
  previewCardButton.textContent = "Preview Anki card";
}

function toggleCardPreview() {
  if (!state.activeToken) return;
  const willShow = cardPreview.hidden;
  if (willShow) renderCardPreview(ankiCardForActiveToken());
  cardPreview.hidden = !willShow;
  previewCardButton.setAttribute("aria-expanded", String(willShow));
  previewCardButton.textContent = willShow ? "Hide Anki card preview" : "Preview Anki card";
  if (activeAnchor) positionPopover(activeAnchor);
}

function ankiCardForActiveToken() {
  const entry = tokenCatalogEntry(state.activeToken);
  const counts = state.sessionCounts.get(entry.canonical) ?? {
    encounters: 0,
    recognitions: 0,
  };
  const encounters = counts.encounters;
  const recognized = counts.recognitions;
  const unrecognized = Math.max(0, encounters - recognized);
  const reviewState = reviewStateForToken(
    entry.canonical,
    recognized,
    unrecognized,
  );
  return ankiCardFromRow({
    ...entry,
    recognitions: recognized,
    unrecognized,
    reviewState,
    priorityDays: reviewPriorityDays(reviewState, recognized, unrecognized),
  });
}

function renderCardPreview(card) {
  cardPreviewExpression.textContent = card.expression;
  cardPreviewReading.textContent = card.hiragana || "Reading unavailable";
  cardPreviewRomaji.textContent = card.romaji || "Romaji unavailable";
  cardPreviewMeaning.textContent = card.translation || "Translation unavailable";
  cardPreviewSurface.textContent = card.surface && card.surface !== card.expression
    ? `Seen as: ${card.surface}`
    : "";
  cardPreviewSentence.textContent = card.sentence || "";
  cardPreviewSentenceRomaji.textContent = card.sentence_romaji || "";
  cardPreviewSentenceTranslation.textContent = card.sentence_translation || "";
  cardPreviewSource.textContent = card.article_title
    ? `Source: ${card.article_title}`
    : "";
  cardPreviewSource.href = card.source_url || "";
  cardPreviewSource.hidden = !(card.article_title && card.source_url);
  cardPreviewDictionary.textContent = [card.dictionary_source, card.vocabulary_id]
    .filter(Boolean)
    .join(" · ");
  if (card.review_state === "easy") {
    cardPreviewAnswer.textContent = "Always recognized · suppressed from Anki";
    return;
  }
  const score = `${card.recognized_count} recognized / ${card.unrecognized_count} unrecognized`;
  const priority = card.priority_days
    ? ` · due in ${card.priority_days} day${card.priority_days === 1 ? "" : "s"}`
    : "";
  cardPreviewAnswer.textContent = `Current session answer: ${ankiAnswerLabel(card.review_state)} · ${score}${priority}`;
}

function ankiAnswerLabel(reviewState) {
  if (reviewState === "easy") return "Easy";
  if (reviewState === "good") return "Good";
  return "Again";
}

function positionPopover(anchor, event) {
  const gap = 8;
  const edge = 12;
  const rect = anchor.getBoundingClientRect();
  const pointer =
    event && Number.isFinite(event.clientX) && Number.isFinite(event.clientY)
      ? { x: event.clientX, y: event.clientY }
      : { x: rect.left + rect.width / 2, y: rect.bottom };
  const popoverHeight = popover.offsetHeight;
  const popoverWidth = popover.offsetWidth;
  let top = pointer.y + gap;
  if (top + popoverHeight > window.innerHeight - edge) {
    top = pointer.y - popoverHeight - gap;
  }
  let left = pointer.x + gap;
  if (left + popoverWidth > window.innerWidth - edge) {
    left = pointer.x - popoverWidth - gap;
  }
  popover.style.top = `${Math.max(edge, top)}px`;
  popover.style.left = `${Math.max(edge, left)}px`;
}

async function chooseToken(token, choice) {
  if (choice === "always") {
    await chooseAlwaysRecognized(token);
  } else {
    const suppressed = affectedTokenEntries(token)
      .map((item) => item.canonical)
      .filter((canonical) => state.alwaysRecognized.has(canonical));
    if (suppressed.length > 0) {
      await persistAlwaysRecognized({ tokenIds: suppressed, enabled: false });
    }
    logSentenceChoice(token, choice);
  }
  hidePopover();
  render();
}

function logSentenceChoice(token, choice) {
  const sentenceId = token.sentenceId;
  const key = markKey(sentenceId, token.canonical);
  const previous = state.sentenceMarks.get(key);
  const affected = affectedTokenEntries(token);
  if (previous === choice) return;
  if (previous) {
    for (const item of affected) decrement(item.canonical, previous);
  }
  const order = ++state.nextSentenceMarkOrder;
  for (const item of affected) {
    registerTokenCatalog(item);
    const itemKey = markKey(sentenceId, item.canonical);
    state.sentenceMarks.set(itemKey, choice);
    state.sentenceMarkOrder.set(itemKey, order);
    increment(item.canonical, choice);
  }
}

async function chooseAlwaysRecognized(token) {
  const affected = affectedTokenEntries(token);
  for (const item of affected) {
    registerTokenCatalog(item);
  }
  const cards = affected.map((item) => ankiCardFromRow({
    ...item,
    recognitions: 0,
    unrecognized: 0,
    reviewState: "easy",
    priorityDays: null,
  }));
  await persistAlwaysRecognized({ cards, enabled: true });
}

async function persistAlwaysRecognized({
  cards = null,
  tokenIds = null,
  enabled,
}) {
  const body = { enabled };
  if (cards) body.cards = cards;
  if (tokenIds) body.token_ids = tokenIds;
  const response = await fetch("/api/always-recognized", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "Could not update always-recognized vocabulary.");
  }
  state.alwaysRecognized = new Set(payload.token_ids || []);
}

function markSentenceViewed(sentence) {
  if (!state.viewedSentenceIds.has(sentence.id)) {
    state.viewedSentenceIds.add(sentence.id);
  }
}

function increment(canonical, choice) {
  const counts = state.sessionCounts.get(canonical) ?? {
    encounters: 0,
    recognitions: 0,
  };
  counts.encounters += 1;
  if (choice === "recognized") counts.recognitions += 1;
  state.sessionCounts.set(canonical, counts);
}

function decrement(canonical, choice) {
  const counts = state.sessionCounts.get(canonical);
  if (!counts) return;
  counts.encounters = Math.max(0, counts.encounters - 1);
  if (choice === "recognized") {
    counts.recognitions = Math.max(0, counts.recognitions - 1);
  }
  state.sessionCounts.set(canonical, counts);
}

function affectedTokenEntries(token) {
  const values = [tokenCatalogEntry(token)];
  for (const inherited of token.inherited_tokens ?? []) {
    values.push(tokenCatalogEntry({
      ...inherited,
      sentenceText: token.sentenceText,
    }));
  }
  const seen = new Set();
  return values.filter((item) => {
    if (seen.has(item.canonical)) return false;
    seen.add(item.canonical);
    return true;
  });
}

function tokenCatalogEntry(token) {
  return {
    canonical: token.canonical,
    surface: token.surface || token.canonical.split("::", 1)[0],
    hiragana: token.hiragana || "",
    romaji: token.romaji || "",
    translation: token.translation || "",
    places: token.places ?? [],
    vocabulary: token.vocabulary ?? null,
    sentence: token.sentenceText || "",
  };
}

function registerTokenCatalog(entry) {
  if (!entry?.canonical || state.tokenCatalog.has(entry.canonical)) return;
  state.tokenCatalog.set(entry.canonical, entry);
}

function renderSessionSummary() {
  const rows = sessionSummaryRows();
  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "summary-row";
    empty.textContent = "No token encounters logged in this session.";
    sessionSummaryList.replaceChildren(empty);
    renderAnkiSyncStatus();
    return;
  }
  sessionSummaryList.replaceChildren(...rows.map(summaryRowElement));
  renderAnkiSyncStatus();
}

function sessionSummaryRows() {
  return [...state.tokenCatalog.values()].map((entry) => {
    const counts = state.sessionCounts.get(entry.canonical) ?? {
      encounters: 0,
      recognitions: 0,
    };
    const encounters = counts.encounters;
    const recognized = counts.recognitions;
    const unrecognized = Math.max(0, encounters - recognized);
    const reviewState = reviewStateForToken(
      entry.canonical,
      recognized,
      unrecognized,
    );
    return {
      ...entry,
      encounters,
      recognitions: recognized,
      unrecognized,
      decisions: counts.encounters,
      reviewState,
      priorityDays: reviewPriorityDays(reviewState, recognized, unrecognized),
    };
  }).filter((row) => (
    row.encounters > 0 || state.alwaysRecognized.has(row.canonical)
  ))
    .sort(compareSessionSummaryRows);
}

function reviewStateForToken(canonical, recognized, unrecognized) {
  if (state.alwaysRecognized.has(canonical)) return "easy";
  return recognized > unrecognized ? "good" : "again";
}

function reviewPriorityDays(reviewState, recognized, unrecognized) {
  if (reviewState !== "good") return null;
  return Math.max(1, recognized - unrecognized);
}

function compareSessionSummaryRows(left, right) {
  const ratioDelta = recognitionValue(left) - recognitionValue(right);
  if (ratioDelta !== 0) return ratioDelta;
  const encounterDelta = left.encounters - right.encounters;
  if (encounterDelta !== 0) return encounterDelta;
  return left.surface.localeCompare(right.surface, "ja");
}

function recognitionValue(row) {
  return row.recognitions / row.encounters;
}

function summaryRowElement(row) {
  const element = document.createElement("div");
  element.className = "summary-row";

  const token = document.createElement("div");
  token.className = "summary-token";
  const surface = document.createElement("div");
  surface.className = "summary-surface";
  surface.textContent = row.surface;
  const meta = document.createElement("div");
  meta.className = "summary-meta";
  meta.textContent = summaryMeta(row);
  token.append(surface, meta);

  const encounters = document.createElement("div");
  encounters.className = "summary-number";
  encounters.textContent = String(row.encounters);

  const recognition = document.createElement("div");
  recognition.className = "summary-number";
  recognition.textContent = recognitionRatio(row);

  element.append(token, encounters, recognition);
  return element;
}

function summaryMeta(row) {
  const reading = [row.hiragana, row.romaji].filter(Boolean).join(" · ");
  const answer = row.reviewState === "easy"
    ? "Always recognized: not sent to Anki"
    : row.reviewState === "good" ? "Anki: Good" : "Anki: Again";
  const score = `score: ${row.recognitions} recognized / ${row.unrecognized} unrecognized`;
  const priority = row.priorityDays
    ? `due priority: ${row.priorityDays} day${row.priorityDays === 1 ? "" : "s"}`
    : "";
  return [row.canonical, reading, row.translation, score, answer, priority]
    .filter(Boolean)
    .join(" | ");
}

function recognitionRatio(row) {
  if (row.encounters === 0) return "—";
  return `${row.recognitions}/${row.encounters}`;
}

async function persistEncounteredPlaces() {
  const places = encounteredPlaces();
  if (places.length === 0) return;
  const response = await fetch("/api/place-cache", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ places }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "Could not cache encountered places.");
  }
}

function renderAnkiSyncStatus() {
  const plan = ankiSyncPlan();
  if (plan.candidates.length === 0) {
    const suppressed = plan.summaryCards.length;
    ankiSyncStatus.textContent = suppressed > 0
      ? `Anki: no cards to sync; ${suppressed} always-recognized token(s) suppressed.`
      : "Anki: no marked vocabulary to sync.";
    confirmEndButton.textContent = "End Session";
    return;
  }
  const counts = reviewStateCounts(plan.ready);
  const incomplete = plan.incomplete.length > 0
    ? ` ${plan.incomplete.length} token(s) are missing a reading or translation; sync is blocked.`
    : "";
  const suppressed = plan.summaryCards.length - plan.candidates.length;
  const suppression = suppressed > 0
    ? ` ${suppressed} always-recognized token(s) suppressed.`
    : "";
  ankiSyncStatus.textContent = `Anki: ${plan.ready.length} token(s) ready — ${counts.again} Again, ${counts.good} Good.${suppression}${incomplete}`;
  confirmEndButton.textContent = plan.incomplete.length === 0
    ? `End Session & Sync ${plan.ready.length} Token${plan.ready.length === 1 ? "" : "s"}`
    : "Cannot End: Incomplete Tokens";
  confirmEndButton.disabled = plan.incomplete.length > 0;
}

function ankiSyncPlan() {
  const summaryCards = sessionSummaryRows().map(ankiCardFromRow);
  const candidates = summaryCards.filter((card) => card.review_state !== "easy");
  return {
    summaryCards,
    candidates,
    ready: candidates.filter(ankiCardIsReady),
    incomplete: candidates.filter((card) => !ankiCardIsReady(card)),
  };
}

function ankiCardFromRow(row) {
  const vocabulary = row.vocabulary ?? {};
  const canonical = row.canonical;
  const context = referenceContextFields(canonical);
  return {
    canonical,
    expression: displayExpression(row),
    surface: context.surface,
    hiragana: vocabulary.hiragana || row.hiragana,
    romaji: vocabulary.romaji || row.romaji,
    translation: vocabulary.translation || row.translation,
    meaning_key: vocabulary.dictionary_id || `UniDic:${canonical}`,
    sentence: context.sentence,
    sentence_romaji: context.sentenceRomaji,
    sentence_translation: context.sentenceTranslation,
    article_title: state.article?.title || "",
    source_url: state.article?.canonicalurl || "",
    vocabulary_id: vocabulary.dictionary_id || `UniDic:${canonical}`,
    dictionary_source: vocabulary.source || "UniDic",
    review_state: row.reviewState,
    recognized_count: row.recognitions,
    unrecognized_count: row.unrecognized,
    priority_days: row.priorityDays,
  };
}

function referenceContextFields(canonical) {
  if (state.alwaysRecognized.has(canonical)) {
    return {
      surface: "",
      sentence: "",
      sentenceRomaji: "",
      sentenceTranslation: "",
    };
  }
  const pairs = [];
  const occurrences = tokenOccurrences(canonical)
    .map((occurrence) => {
      const key = markKey(occurrence.sentenceId, canonical);
      return {
        ...occurrence,
        key,
        choice: state.sentenceMarks.get(key),
        order: state.sentenceMarkOrder.get(key) ?? 0,
      };
    })
    .filter((occurrence) => (
      occurrence.choice === "recognized" || occurrence.choice === "unrecognized"
    ))
    .sort((left, right) => left.order - right.order);
  for (const occurrence of occurrences) {
    const surface = occurrence.surface.trim();
    const sentence = occurrence.sentence.trim();
    const sentenceRomaji = occurrence.sentenceRomaji.trim();
    const sentenceTranslation = occurrence.sentenceTranslation.trim();
    if (!surface && !sentence) continue;
    const existing = pairs.findIndex((item) => (
      item.surface === surface && item.sentence === sentence
    ));
    if (existing >= 0) pairs.splice(existing, 1);
    pairs.push({ surface, sentence, sentenceRomaji, sentenceTranslation });
  }
  const recent = pairs.slice(-5);
  return {
    surface: recent.map((item) => item.surface).join("\n"),
    sentence: recent.map((item) => item.sentence).join("\n"),
    sentenceRomaji: recent.map((item) => item.sentenceRomaji).join("\n"),
    sentenceTranslation: recent.map((item) => item.sentenceTranslation).join("\n"),
  };
}

function displayExpression(row) {
  const vocabulary = row.vocabulary ?? {};
  const canonical = row.canonical.split("::", 1)[0];
  const mapped = String(vocabulary.headword || canonical).trim() || canonical;
  if (vocabulary.source === "Local override") return mapped;
  if (/^[ぁ-ゖァ-ヺー]+$/.test(canonical)) return canonical;

  const occurrences = tokenOccurrences(row.canonical).reverse();
  const exact = occurrences.find((item) => (
    item.surface === mapped || item.surface === canonical
  ));
  if (exact) return exact.surface;

  const reading = normalizedJapaneseReading(vocabulary.hiragana || row.hiragana);
  const kana = occurrences.find((item) => (
    /^[ぁ-ゖァ-ヺー]+$/.test(item.surface)
      && normalizedJapaneseReading(item.surface) === reading
  ));
  return kana?.surface || mapped;
}

function tokenOccurrences(canonical) {
  const occurrences = [];
  for (const sentence of state.article?.sentences ?? []) {
    if (!state.viewedSentenceIds.has(sentence.id)) continue;
    const aid = state.sentenceAidCache.get(sentenceAidKey(sentence))
      ?? sentence.sentence_aid
      ?? {};
    const sentenceCanonicals = new Set();
    for (const token of sentence.tokens) {
      const entries = affectedTokenEntries({
        ...token,
        sentenceId: sentence.id,
        sentenceText: sentence.display_text,
      });
      for (const entry of entries) {
        if (entry.canonical !== canonical || sentenceCanonicals.has(canonical)) continue;
        sentenceCanonicals.add(canonical);
        occurrences.push({
          sentenceId: sentence.id,
          surface: String(entry.surface || ""),
          sentence: String(sentence.display_text || ""),
          sentenceRomaji: String(aid.romaji || ""),
          sentenceTranslation: String(aid.english || ""),
        });
      }
    }
  }
  return occurrences;
}

function normalizedJapaneseReading(value) {
  return String(value).replace(/[ァ-ヶ]/g, (character) => (
    String.fromCodePoint(character.codePointAt(0) - 0x60)
  )).replace(/\s+/g, "");
}

function ankiCardIsReady(card) {
  const sentenceCount = contextLineCount(card.sentence);
  const contextsReady = sentenceCount === 0 || (
    contextLineCount(card.sentence_romaji) === sentenceCount
      && contextLineCount(card.sentence_translation) === sentenceCount
  );
  return Boolean(
    card.canonical
      && card.expression
      && card.hiragana
      && card.romaji
      && card.translation
      && contextsReady
  );
}

function contextLineCount(value) {
  if (!String(value || "").trim()) return 0;
  return String(value).split("\n").length;
}

function reviewStateCounts(cards) {
  const counts = { again: 0, good: 0, easy: 0 };
  for (const card of cards) counts[card.review_state] += 1;
  return counts;
}

async function refreshAnkiStatus() {
  const plan = ankiSyncPlan();
  if (plan.candidates.length === 0 || plan.incomplete.length > 0) return;
  const summary = ankiSyncStatus.textContent;
  ankiSyncStatus.textContent = `${summary} Checking AnkiConnect…`;
  const response = await fetch("/api/anki/status");
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.connected) {
    ankiSyncStatus.textContent = `${summary} ${payload.error || "AnkiConnect is unavailable."}`;
    return;
  }
  ankiSyncStatus.textContent = `${summary} Connected to ${payload.deck}.`;
}

async function syncAnkiSession({ checkpoint = false } = {}) {
  const plan = ankiSyncPlan();
  if (plan.summaryCards.length === 0) {
    return {
      tokens: 0,
      created: 0,
      updated: 0,
      scheduled: {},
      already_logged: 0,
      checkpoint,
      ended: !checkpoint,
    };
  }
  if (plan.incomplete.length > 0) {
    const action = checkpoint ? "logged" : "ended";
    throw new Error(
      `${plan.incomplete.length} token(s) are missing a reading or translation; the session was not ${action}.`,
    );
  }
  const endpoint = checkpoint ? "/api/anki-checkpoint" : "/api/anki-sync";
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: state.sessionId,
      cards: plan.ready,
      summary_cards: plan.summaryCards,
    }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "Could not sync the session to Anki.");
  }
  return response.json();
}

function ankiSyncResultLabel(result) {
  const scheduled = result.scheduled ?? {};
  const action = result.checkpoint ? "logged" : "synced";
  const unchanged = result.already_logged ?? 0;
  return `Anki ${action} ${result.tokens ?? 0} changed token(s): ${result.created ?? 0} added, ${result.updated ?? 0} updated; ${scheduled.again ?? 0} Again, ${scheduled.good ?? 0} Good; ${unchanged} unchanged.`;
}

function encounteredPlaces() {
  const places = new Map();
  for (const entry of state.tokenCatalog.values()) {
    if ((state.sessionCounts.get(entry.canonical)?.encounters ?? 0) <= 0) continue;
    for (const place of entry.places ?? []) {
      const key = place.id || place.surface || place.label;
      if (!key) continue;
      places.set(key, place);
    }
  }
  return [...places.values()];
}

function phraseLabel(token) {
  const phrases = token.phrases ?? [];
  if (phrases.length === 0) return "";
  return `phrase: ${phrases
    .map((item) => `${item.surface} → ${item.translation}`)
    .join("; ")}`;
}

function placeLabel(token) {
  const places = token.places ?? [];
  if (places.length === 0) return "";
  return `place: ${places
    .map((item) => `${item.english_label || item.label || item.surface} (${item.id})`)
    .join(", ")}`;
}

function readingLabel(token) {
  if (token.reading_status === "missing") return "reading unavailable";
  const source = readingSourceLabel(token);
  if (token.reading_status === "partial") {
    return `${token.hiragana} · ${token.romaji} (partial reading${source})`;
  }
  if (!token.hiragana && !token.romaji) return "reading unavailable";
  return `${token.hiragana} · ${token.romaji}${source}`;
}

function readingSourceLabel(token) {
  if (token.reading_status !== "wikimedia") return "";
  const title = token.reading_source?.title;
  return title ? ` (Wikimedia: ${title})` : " (Wikimedia)";
}

function inheritedLabel(token) {
  const inherited = token.inherited_tokens ?? [];
  if (inherited.length === 0) return "";
  return `also logs: ${inherited.map(inheritedSummary).join(", ")}`;
}

function inheritedSummary(item) {
  if (!item.translation) return item.canonical;
  return `${item.canonical} (${item.translation})`;
}

function currentSentence() {
  return state.article.sentences[state.index];
}

function markKey(sentenceId, canonical) {
  return `${sentenceId}\u0000${canonical}`;
}

function setTheme(theme) {
  const isDark = theme === "dark";
  document.body.classList.toggle("dark", isDark);
  themeLightButton.setAttribute("aria-pressed", String(!isDark));
  themeDarkButton.setAttribute("aria-pressed", String(isDark));
  localStorage.setItem("wikiReaderTheme", isDark ? "dark" : "light");
}

window.addEventListener("pagehide", persistActiveSession);
