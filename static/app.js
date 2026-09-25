const state = {
  article: null,
  index: 0,
  sentenceMarks: new Map(),
  alwaysRecognized: new Set(),
  sessionCounts: new Map(),
  viewedCounts: new Map(),
  globalCounts: new Map(),
  viewedSentenceIds: new Set(),
  alwaysLoggedKeys: new Set(),
  tokenCatalog: new Map(),
  activeToken: null,
  sessionId: null,
};

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
const previousButton = document.querySelector("#previous");
const nextButton = document.querySelector("#next");
const endSessionButton = document.querySelector("#end-session");
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
const cardPreviewSource = document.querySelector("#card-preview-source");
const cardPreviewDictionary = document.querySelector("#card-preview-dictionary");
const cardPreviewAnswer = document.querySelector("#card-preview-answer");
const confirmOverlay = document.querySelector("#confirm");
const cancelEndButton = document.querySelector("#cancel-end");
const confirmEndButton = document.querySelector("#confirm-end");
const sessionSummaryList = document.querySelector("#session-summary-list");
const ankiSyncStatus = document.querySelector("#anki-sync-status");
let popoverCloseTimer = null;
let activeAnchor = null;
let lastPointer = { x: 0, y: 0 };

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
themeLightButton.addEventListener("click", () => setTheme("light"));
themeDarkButton.addEventListener("click", () => setTheme("dark"));
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
  chooseToken(state.activeToken, button.dataset.choice);
});
popover.addEventListener("mouseenter", cancelPopoverClose);
popover.addEventListener("mouseleave", schedulePopoverClose);

document.addEventListener("click", (event) => {
  if (event.target.closest(".token") || event.target.closest("#popover")) return;
  hidePopover();
});
document.addEventListener("mousemove", (event) => {
  lastPointer = { x: event.clientX, y: event.clientY };
  if (!popover.hidden && pointerInsidePopoverArea(lastPointer.x, lastPointer.y)) {
    cancelPopoverClose();
  } else if (!popover.hidden && !popoverCloseTimer) {
    schedulePopoverClose();
  }
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
    const article = await waitForArticleJob(startPayload.job_id);
    startSession(article);
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
    const message = total > 0
      ? `Analyzing sentence ${processed} of ${total}...`
      : payload.message || "Loading article...";
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

function startSession(article) {
  state.article = article;
  state.index = 0;
  state.sentenceMarks = new Map();
  state.alwaysRecognized = new Set();
  state.sessionCounts = new Map();
  state.viewedCounts = new Map();
  state.viewedSentenceIds = new Set();
  state.alwaysLoggedKeys = new Set();
  state.tokenCatalog = new Map();
  state.activeToken = null;
  state.sessionId = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  articleTitle.textContent = article.title;
  landing.hidden = true;
  reader.hidden = false;
  sessionFooter.hidden = false;
  formStatus.textContent = "";
  render();
}

function resetToLanding() {
  hidePopover();
  state.article = null;
  sessionSummaryList.replaceChildren();
  articleTitle.textContent = "Wikipedia Sentence Reader";
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
  previousButton.disabled = state.index === 0;
  nextButton.disabled = state.index === state.article.sentences.length - 1;
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
    span.textContent = sentence.display_text.slice(range.start, range.end);
    span.addEventListener("mouseenter", (event) => showPopover(event.currentTarget, token, event));
    span.addEventListener("mouseleave", schedulePopoverClose);
    span.addEventListener("focus", (event) => showPopover(event.currentTarget, token, event));
    span.addEventListener("blur", schedulePopoverClose);
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
  cancelPopoverClose();
  resetCardPreview();
  activeAnchor = anchor;
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

function schedulePopoverClose() {
  cancelPopoverClose();
  popoverCloseTimer = window.setTimeout(() => {
    if (!popoverShouldStayOpen()) {
      hidePopover();
    }
  }, 260);
}

function cancelPopoverClose() {
  if (popoverCloseTimer) {
    window.clearTimeout(popoverCloseTimer);
    popoverCloseTimer = null;
  }
}

function hidePopover() {
  cancelPopoverClose();
  resetCardPreview();
  popover.hidden = true;
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
  return ankiCardFromRow({
    ...entry,
    reviewState: reviewStateForToken(entry.canonical, counts),
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
  cardPreviewSource.textContent = card.article_title
    ? `Source: ${card.article_title}`
    : "";
  cardPreviewSource.href = card.source_url || "";
  cardPreviewSource.hidden = !(card.article_title && card.source_url);
  cardPreviewDictionary.textContent = [card.dictionary_source, card.vocabulary_id]
    .filter(Boolean)
    .join(" · ");
  cardPreviewAnswer.textContent = `Current session answer: ${ankiAnswerLabel(card.review_state)}`;
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
      : lastPointer;
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

function popoverShouldStayOpen() {
  if (popover.matches(":hover")) return true;
  if (activeAnchor?.matches(":hover")) return true;
  if (document.activeElement === activeAnchor) return true;
  if (document.activeElement.closest?.("#popover")) return true;
  return pointerInsidePopoverArea(lastPointer.x, lastPointer.y);
}

function pointerInsidePopoverArea(x, y) {
  if (!activeAnchor || popover.hidden) return false;
  const anchorRect = activeAnchor.getBoundingClientRect();
  const popoverRect = popover.getBoundingClientRect();
  return pointInsideExpandedRect(x, y, anchorRect, 8)
    || pointInsideExpandedRect(x, y, popoverRect, 8)
    || pointInsideBridge(x, y, anchorRect, popoverRect);
}

function pointInsideExpandedRect(x, y, rect, padding) {
  return x >= rect.left - padding
    && x <= rect.right + padding
    && y >= rect.top - padding
    && y <= rect.bottom + padding;
}

function pointInsideBridge(x, y, anchorRect, popoverRect) {
  const padding = 24;
  const left = Math.min(anchorRect.left, popoverRect.left) - padding;
  const right = Math.max(anchorRect.right, popoverRect.right) + padding;
  const top = Math.min(anchorRect.bottom, popoverRect.bottom) - padding;
  const bottom = Math.max(anchorRect.top, popoverRect.top) + padding;
  return x >= left && x <= right && y >= top && y <= bottom;
}

function chooseToken(token, choice) {
  if (choice === "always") {
    chooseAlwaysRecognized(token);
  } else {
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
  for (const item of affected) {
    registerTokenCatalog(item);
    state.sentenceMarks.set(markKey(sentenceId, item.canonical), choice);
    increment(item.canonical, choice);
  }
}

function chooseAlwaysRecognized(token) {
  const affected = affectedTokenEntries(token);
  for (const item of affected) {
    registerTokenCatalog(item);
    state.alwaysRecognized.add(item.canonical);
  }
  logAlwaysRecognizedForViewedSentences(affected.map((item) => item.canonical));
}

function logAlwaysRecognizedForViewedSentences(canonicals) {
  const canonicalSet = new Set(canonicals);
  for (const sentence of state.article.sentences) {
    if (!state.viewedSentenceIds.has(sentence.id)) continue;
    logAlwaysRecognizedForSentence(sentence, canonicalSet);
  }
}

function logAlwaysRecognizedForSentence(sentence, canonicalSet = state.alwaysRecognized) {
  for (const token of sentence.tokens) {
    for (const item of affectedTokenEntries({
      ...token,
      sentenceId: sentence.id,
      sentenceText: sentence.display_text,
    })) {
      if (!canonicalSet.has(item.canonical)) continue;
      registerTokenCatalog(item);
      const key = markKey(sentence.id, item.canonical);
      if (state.alwaysLoggedKeys.has(key)) continue;
      const previous = state.sentenceMarks.get(key);
      if (previous) {
        decrement(item.canonical, previous);
      }
      state.sentenceMarks.set(key, "recognized");
      increment(item.canonical, "recognized");
      state.alwaysLoggedKeys.add(key);
    }
  }
}

function markSentenceViewed(sentence) {
  if (!state.viewedSentenceIds.has(sentence.id)) {
    state.viewedSentenceIds.add(sentence.id);
    const sentenceCanonicals = new Set();
    for (const token of sentence.tokens) {
      for (const item of affectedTokenEntries({
        ...token,
        sentenceId: sentence.id,
        sentenceText: sentence.display_text,
      })) {
        registerTokenCatalog(item);
        sentenceCanonicals.add(item.canonical);
      }
    }
    for (const canonical of sentenceCanonicals) {
      state.viewedCounts.set(canonical, (state.viewedCounts.get(canonical) ?? 0) + 1);
    }
  }
  logAlwaysRecognizedForSentence(sentence);
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
    return {
      ...entry,
      encounters: state.viewedCounts.get(entry.canonical) ?? 0,
      recognitions: counts.recognitions,
      decisions: counts.encounters,
      reviewState: reviewStateForToken(entry.canonical, counts),
    };
  }).filter((row) => row.encounters > 0)
    .sort(compareSessionSummaryRows);
}

function reviewStateForToken(canonical, counts) {
  if (state.alwaysRecognized.has(canonical)) return "easy";
  const viewed = state.viewedCounts.get(canonical) ?? 0;
  if (viewed > 0 && counts.encounters === viewed && counts.recognitions === viewed) {
    return "good";
  }
  return "again";
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
    ? "Anki: Easy"
    : row.reviewState === "good" ? "Anki: Good" : "Anki: Again";
  return [row.canonical, reading, row.translation, answer].filter(Boolean).join(" | ");
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
    ankiSyncStatus.textContent = "Anki: no viewed vocabulary to sync.";
    confirmEndButton.textContent = "End Session";
    return;
  }
  const counts = reviewStateCounts(plan.ready);
  const incomplete = plan.incomplete.length > 0
    ? ` ${plan.incomplete.length} token(s) are missing a reading or translation; sync is blocked.`
    : "";
  ankiSyncStatus.textContent = `Anki: ${plan.ready.length} token(s) ready — ${counts.again} Again, ${counts.good} Good, ${counts.easy} Easy.${incomplete}`;
  confirmEndButton.textContent = plan.incomplete.length === 0
    ? `End Session & Sync ${plan.ready.length} Token${plan.ready.length === 1 ? "" : "s"}`
    : "Cannot End: Incomplete Tokens";
  confirmEndButton.disabled = plan.incomplete.length > 0;
}

function ankiSyncPlan() {
  const candidates = sessionSummaryRows()
    .map(ankiCardFromRow);
  return {
    candidates,
    ready: candidates.filter(ankiCardIsReady),
    incomplete: candidates.filter((card) => !ankiCardIsReady(card)),
  };
}

function ankiCardFromRow(row) {
  const vocabulary = row.vocabulary ?? {};
  const canonical = row.canonical;
  return {
    canonical,
    expression: canonical.split("::", 1)[0],
    surface: row.surface,
    hiragana: vocabulary.hiragana || row.hiragana,
    romaji: vocabulary.romaji || row.romaji,
    translation: vocabulary.translation || row.translation,
    sentence: row.sentence,
    article_title: state.article?.title || "",
    source_url: state.article?.canonicalurl || "",
    vocabulary_id: vocabulary.dictionary_id || `UniDic:${canonical}`,
    dictionary_source: vocabulary.source || "UniDic",
    review_state: row.reviewState,
  };
}

function ankiCardIsReady(card) {
  return Boolean(
    card.canonical
      && card.expression
      && card.hiragana
      && card.romaji
      && card.translation,
  );
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

async function syncAnkiSession() {
  const plan = ankiSyncPlan();
  if (plan.candidates.length === 0) {
    return { tokens: 0, created: 0, updated: 0, scheduled: {} };
  }
  if (plan.incomplete.length > 0) {
    throw new Error(
      `${plan.incomplete.length} token(s) are missing a reading or translation; the session was not ended.`,
    );
  }
  const response = await fetch("/api/anki-sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.sessionId, cards: plan.ready }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "Could not sync the session to Anki.");
  }
  return response.json();
}

function ankiSyncResultLabel(result) {
  const scheduled = result.scheduled ?? {};
  return `Anki synced ${result.tokens ?? 0} token(s): ${result.created ?? 0} added, ${result.updated ?? 0} updated; ${scheduled.again ?? 0} Again, ${scheduled.good ?? 0} Good, ${scheduled.easy ?? 0} Easy.`;
}

function encounteredPlaces() {
  const places = new Map();
  for (const entry of state.tokenCatalog.values()) {
    if ((state.viewedCounts.get(entry.canonical) ?? 0) <= 0) continue;
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
