# Private Japanese Text → Review Deck Protocol

This is the repeatable workflow for a Japanese article, essay, or fiction text
that you lawfully access and keep for private study. It deliberately keeps the
downloaded source, extracted text, vocabulary overrides, and generated reader
copy outside Git.

## 0. One-time setup

```bash
python -m pip install -e ".[dev]"
python scripts/build_dictionary_index.py
```

In Anki, install AnkiConnect add-on `2055492159`, restart Anki, and leave Anki
running while ending a reading session. The reader talks only to AnkiConnect's
loopback endpoint (`127.0.0.1:8765`) and never writes `collection.anki2`
directly.

The reader owns one note type and one deck:

- note type: `Japanese Sentence Reader`
- deck: `Japanese::Sentence Reader`

## 1. Download a lawful private copy

Save a PDF, HTML page, or plain-text copy outside the repository. Use content
that is publicly available to you or that you are otherwise authorized to
access. Do not bypass authentication, a paywall, DRM, or other access controls.
Do not commit or redistribute the downloaded page or extracted article.

The same local workflow can be used for downloaded 小説 and other fiction when
your access and private-copy use are lawful. Keep the source private, respect
the publisher's terms, and do not use the reader to redistribute the text.

## 2. Stage the article

```bash
ja-reader-import stage "/absolute/path/to/download.pdf" \
  --key short-lowercase-key \
  --title "Article title" \
  --url "https://publisher.example/article" \
  --pages 1-4
```

For noisy downloads, exact boundaries can be applied during extraction:

```bash
ja-reader-import stage "/absolute/path/to/download.html" \
  --key short-lowercase-key \
  --title "Article title" \
  --url "https://publisher.example/article" \
  --start-marker "first article words" \
  --end-marker "first footer words"
```

This creates the ignored draft:

```text
data/private/imports/<key>/article.txt
```

## 3. Review the extraction

Open `article.txt` and remove navigation, subscription prompts, page furniture,
captions that are not part of the article, and accidental duplicate text. Keep
the intended Japanese article body and sentence punctuation. Full article text
must remain under `data/private/`.

If tokenization exposes a genuinely missing or article-specific term, add its
headword, reading, romaji, and English gloss to the ignored file:

```text
data/private/vocabulary_overrides.json
```

## 4. Finalize and validate

```bash
ja-reader-import finalize short-lowercase-key --reviewed
```

The command creates and validates:

```text
data/private/articles/<key>.json
```

Open it in the reader at:

```text
http://127.0.0.1:5001/?article=private%3A<key>
```

## 5. Read and mark tokens

Each sentence has a **Reveal romaji + English** control beneath it. The reveal
is instant after the article loads. On the first load, all missing sentence aids
are generated in consistent batches through the locally configured Codex CLI,
using immediate adjacent context, and persisted in `data/sentence_aids.sqlite`.
Later loads do not invoke the CLI for those sentences. These aids are
display-only and never affect recognition counts or Anki synchronization.

Only explicitly marked tokens are included at Log Session or End Session.
Merely displaying or navigating through a sentence does not track its tokens.
Repeated marked occurrences of the same canonical token are combined before
scheduling.

| Reader result | Anki answer | Effect |
| --- | --- | --- |
| unrecognized is greater than or equal to recognized | Again (`1`) | enters review/relearning at highest priority |
| recognized is greater than unrecognized | Good (`3`) | due in `recognized - unrecognized` days |
| always recognized | no Anki answer | persistently highlighted and completely suppressed from Anki |

For a recognized majority, the positive difference is the priority margin. A
1-vote margin is due in 1 day; a 5-vote margin is due in 5 days. This keeps
borderline vocabulary ahead of consistently recognized vocabulary. A tie is
handled conservatively as Again.

If a token is absent from the deck, its note is created. If its card is New or
in a learning queue, it is first promoted to Review. The answer is then applied
through Anki's scheduler. Consequently the deck contains no New cards after a
successful sync; Again cards may correctly enter Anki's *relearning* queue.

**Always recognized** is a project-wide suppression state rather than an Anki
grade. Its canonical token ID persists locally, so every occurrence in the
current article and future articles receives the always-recognized highlight.
The reader never creates, updates, schedules, or answers an Anki card for that
token. Explicitly choosing **recognized** or **unrecognized** later clears the
suppression state.

The note keeps the canonical `lemma::POS` token ID for deduplication. If an
encountered kana spelling exactly matches the complete mapped reading, that
natural kana spelling is used on the front instead of an uncommon UniDic kanji
lemma. If the canonical lemma itself is kana, it stays in kana instead of being
replaced by an uncommon dictionary kanji spelling (for example, `する`, not
`為る`). Explicit local vocabulary overrides remain authoritative.

The shared token mapping also recovers a validated dictionary lemma for an
untranslated inflected form, rejects JMnedict name homophones for ordinary
inflecting words, and uses productive V-てみる context to reject an unrelated
fixed-expression entry. Independently meaningful dictionary-backed noun
suffixes remain separate selectable tokens inside compounds.

Reference examples form a rolling queue from occurrences explicitly marked
**recognized** or **unrecognized**. Unmarked and always-recognized occurrences
supply no context. The note retains the five most recent distinct examples;
each keeps its observed Surface, original Japanese sentence, full-sentence
romaji, and natural English translation aligned as one record. Seeing the same
Surface/Sentence pair again moves its complete record to the newest position,
and later syncs merge into the same queue. Reveal otherwise shows the token's
hiragana, romaji, English meaning, the retained reference examples, article
link, and dictionary identity.

Polysemous vocabulary retains one canonical card and one combined scheduler
history. Each encountered meaning contribution carries a stable dictionary or
local sense key. Synchronization updates an existing keyed meaning, merges an
exact normalized gloss when a legacy key is absent, and appends only genuinely
new meanings. It does not require an LLM to decide whether the same known sense
has already been stored.

The article and roleplay tools share this note type and token identity while
using separate decks. A sync may move, promote, and answer only the cards in
its current batch; unrelated cards in the other deck are left untouched.

## 6. End only after a successful sync

Use **Log Session** at any point to create or update cards without closing the
reader. It sends only card states that are new or have changed since the last
successful checkpoint. Repeating it without further reading or recognition
changes is a no-op; a failed attempt remains pending for retry.

**End Session** checks every token for the required reading and translation,
then syncs only changes not already logged and closes the reader. It does not
answer unchanged checkpointed cards twice. The local reader is reset only after
all operations succeed. If Anki or AnkiConnect is unavailable, the session
remains open so it can be retried without losing marks.

Use **Summary** to inspect vocabulary across saved article sessions. It shows
recognized, unrecognized, always-recognized, and difference totals with the
same three sorting views as the roleplay reader. The currently open session is
included immediately from browser state; opening the summary does not sync or
reschedule any Anki cards.

## Maintenance

Re-run the dictionary build periodically. It resolves the current
`jmdict-simplified` release and records that release in the generated SQLite
database, which also invalidates older analysis-cache entries:

```bash
python scripts/build_dictionary_index.py
```

JMdict/JMnedict attribution and licensing:

- <https://www.edrdg.org/edrdg/licence.html>
- <https://github.com/scriptin/jmdict-simplified>
