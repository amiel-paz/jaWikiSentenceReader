# Japanese Sentence Reader

Local prototype for reading Japanese text one sentence at a time. It supports
Japanese Wikipedia directly and lawfully obtained articles, essays, and fiction
through the private local import workflow.

The repository and Python package retain the historical `jaWikiSentenceReader`
name so existing installations, the persistent service, and the sibling
roleplay tool continue working without migration.

## What It Does

- Accepts a Japanese Wikipedia article URL/title or a private local text key.
- Fetches article text through the MediaWiki API.
- Shows one sentence at a time.
- Reveals full-sentence romaji and a natural English translation behind a
  spoiler control, batch-generated on first load through the local Codex CLI
  and cached for later visits.
- Tokenizes Japanese terms into canonical tokens.
- Adds readings, romaji, optional JMdict/JMnedict glosses, and contextual phrase hints.
- Adds cached Wikimedia/Wikidata place annotations for likely place-name spans.
- Fills missing kanji readings from cached Japanese Wikipedia parenthetical readings
  when the source can be matched conservatively.
- Tracks session recognition choices in browser memory.
- Previews the exact Anki front/reveal payload from each click-open token panel.
- Syncs explicitly marked tokens into a dedicated, review-only Anki deck.
- Logs new or changed cards to Anki mid-session without closing the reader or
  answering an unchanged card twice.
- Provides a persistent vocabulary summary across reading sessions, including
  the current unsynced session, sortable by recognition, non-recognition, or
  recognition difference.
- Keeps a rolling Anki reference queue from explicitly recognized and
  unrecognized occurrences: the five most recent distinct examples survive,
  and repeated examples move to the newest position. Every retained example
  includes the original Japanese sentence, full-sentence romaji, and its
  natural English translation.
- Treats always-recognized vocabulary as a persistent project-wide suppression
  list: every occurrence stays highlighted, but no Anki card is created,
  updated, scheduled, or answered for it.
- Keeps polysemous vocabulary on one canonical card. Encountered meanings are
  merged by stable dictionary/local sense identity, with normalized gloss text
  as a fallback, so an already-known meaning is not duplicated.
- Uses an encountered kana spelling on the card front when it exactly matches
  the mapped reading, while retaining the stable canonical token ID internally.
- Keeps a kana canonical lemma in kana on the card front instead of replacing
  it with an uncommon dictionary kanji spelling (for example, `する`, not `為る`).
- Repairs untranslated inflected forms to a validated dictionary lemma, rejects
  JMnedict name homophones for ordinary inflecting words, and uses productive
  V-てみる context to reject an unrelated fixed-expression match.
- Exposes independently meaningful, dictionary-backed noun suffixes as their
  own selectable tokens even when UniDic folds them into a larger compound.

Phrase hints are explanatory only. They are not included in session/global recognition accounting.

Sentence reading aids are also display-only. They do not change token tracking,
recognition counts, or Anki cards. On the first article load, all missing romaji
and natural-English sentence aids are generated in consistent batches through
the locally configured Codex CLI and persisted in `data/sentence_aids.sqlite`.
Later loads and reveal actions use the cache and do not invoke the CLI again.

## Run

```bash
python -m pip install -e .
python -m wiki_reader.app
```

Open:

```text
http://127.0.0.1:5001
```

### Persistent macOS Service

To keep the reader available after terminal and Codex sessions end, install its
per-user launch agent:

```bash
./scripts/install_macos_service.sh
```

The service starts at login and restarts automatically if it exits. It remains
local to the Mac at `127.0.0.1:5001`. Logs are written to
`~/Library/Logs/ja-wiki-sentence-reader.log` and
`~/Library/Logs/ja-wiki-sentence-reader.error.log`.

To stop the service and remove the launch agent:

```bash
./scripts/uninstall_macos_service.sh
```

## Private Local Articles

Private article text can be stored in an ignored file at
`data/private/articles/<key>.json` with `title`, `canonicalurl`,
`revision_timestamp`, and `text` fields. Enter `private:<key>` in the reader, or
open `/?article=private:<key>` to load it directly.

Keep complete downloaded pages, extracted article text, images, and publisher
assets under `data/private/`; do not add them to test fixtures or Git. Tracked
tests should use synthetic text or only the smallest excerpt needed to reproduce
a parser bug.

Private vocabulary corrections can be added to the ignored
`data/private/vocabulary_overrides.json`. Each token receives a stable canonical
lemma/POS ID and maps to JMdict, JMnedict, a local override, or an explicit UniDic
fallback.

## Private Article Protocol

Use the reproducible, local-only workflow in
[`docs/PRIVATE_ARTICLE_PROTOCOL.md`](docs/PRIVATE_ARTICLE_PROTOCOL.md). The
`ja-reader-import` command stages PDF, HTML, or text downloads for manual
content review before producing a reader-ready private article.

## Anki Review Sync

Install AnkiConnect add-on `2055492159`, restart Anki, and leave it running while
logging or ending a session. **Log Session** creates or updates every new or
changed token explicitly marked so far while keeping the reader open.
Repeated checkpoints and End Session skip identical card states, so an
unchanged card is not answered twice. **End Session** handles any remaining
changes and closes the reader only after success.

Cards are stored in `Japanese::Sentence Reader`. New and learning cards are
promoted to review before the session answer is applied:

- unmarked occurrences are ignored and do not enter tracking or Anki;
- unrecognized greater than or equal to recognized → Again (`1`);
- recognized greater than unrecognized → Good (`3`), due in a number of days
  equal to the recognition margin;
- always recognized → persistently highlighted and suppressed from Anki.

Choosing recognized or unrecognized later removes the token from the
always-recognized suppression list. Always-recognized encounters never enter
the card's rolling Surface/Sentence reference queue.

Again may put a card into Anki's relearning queue, but no card remains New after
a successful sync. Every card has:

- the canonical Japanese expression on the front;
- hiragana, romaji, and an English translation on reveal;
- up to five marked contexts, each with the observed surface form, original
  Japanese sentence, full-sentence romaji, and natural English translation;
- the article source and vocabulary ID;
- stable canonical-token identity and part-of-speech-aware deduplication.

The reader closes the session only after every card has synced and received its
scheduler answer. The TSV endpoint remains available as a manual diagnostic
fallback, but it cannot apply scheduler state.

The roleplay and article decks share the note type and canonical token identity,
but a sync moves, promotes, and answers only the cards in that sync batch. It
does not move unrelated roleplay cards into the article deck or change their
scheduler state.

The **Summary** tab aggregates tracked vocabulary across successfully logged or
ended reading sessions. While an article is open, its current in-memory state
replaces that session's saved snapshot in the display, so the counts reflect
marks made since the last checkpoint without writing anything to Anki. Sort by
most recognized, most unrecognized, or best recognition difference.

## Optional Dictionary Index

Translations are powered by a generated SQLite index from `jmdict-simplified`,
derived from EDRDG JMdict/JMnedict.

```bash
python scripts/build_dictionary_index.py
```

Generated files live under `data/` and are ignored by git.

Licensing and attribution should follow:

- https://www.edrdg.org/edrdg/licence.html
- https://github.com/scriptin/jmdict-simplified

## Current Prototype Boundaries

- Recognition counts remain in browser memory until they are logged or the
  session ends; Anki retains the actual card history and schedule.
- Always-recognized token IDs persist locally across articles and reader
  restarts, and are excluded from Anki synchronization.
- Direct review scheduling requires Anki and AnkiConnect to be running locally.
- Phrase matching is experimental and shown in the click-open token panel.
- Place annotations are generated from Japanese Wikipedia page hits with Wikidata IDs
  and are cached locally in `data/wikidata_place_cache.sqlite`.
- Wikimedia reading lookups are cached locally in
  `data/wikimedia_reading_cache.sqlite`.
- The dictionary index is optional and rebuilt locally.
