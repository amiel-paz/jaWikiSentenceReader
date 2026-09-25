# jaWikiSentenceReader

Local prototype for reading Japanese Wikipedia articles one sentence at a time.

## What It Does

- Accepts a Japanese Wikipedia article URL/title or a private local article key.
- Fetches article text through the MediaWiki API.
- Shows one sentence at a time.
- Tokenizes Japanese terms into canonical tokens.
- Adds readings, romaji, optional JMdict/JMnedict glosses, and hover-only phrase hints.
- Adds cached Wikimedia/Wikidata place annotations for likely place-name spans.
- Fills missing kanji readings from cached Japanese Wikipedia parenthetical readings
  when the source can be matched conservatively.
- Tracks session recognition choices in browser memory.
- Previews the exact Anki front/reveal payload from each token hover.
- Syncs every token from viewed sentences into a dedicated, review-only Anki deck.

Phrase hints are explanatory only. They are not included in session/global recognition accounting.

## Run

```bash
python -m pip install -e .
python -m wiki_reader.app
```

Open:

```text
http://127.0.0.1:5001
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
ending a session. Every token from every viewed sentence is created or updated
in `Japanese::Sentence Reader`. New and learning cards are promoted to review
before the session answer is applied:

- unmarked occurrences count as unrecognized;
- unrecognized greater than or equal to recognized → Again (`1`);
- recognized greater than unrecognized → Good (`3`), due in a number of days
  equal to the recognition margin;
- always recognized → Easy (`4`).

Again may put a card into Anki's relearning queue, but no card remains New after
a successful sync. Every card has:

- the canonical Japanese expression on the front;
- hiragana, romaji, and an English translation on reveal;
- the observed surface form, source sentence, article source, and vocabulary ID;
- stable canonical-token identity and part-of-speech-aware deduplication.

The reader closes the session only after every card has synced and received its
scheduler answer. The TSV endpoint remains available as a manual diagnostic
fallback, but it cannot apply scheduler state.

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

- Session/global display persistence is in-memory only; Anki retains the actual
  card history and schedule.
- Always-recognized is a per-session choice and maps to Anki Easy at sync.
- Direct review scheduling requires Anki and AnkiConnect to be running locally.
- Phrase matching is experimental and hover-only.
- Place annotations are generated from Japanese Wikipedia page hits with Wikidata IDs
  and are cached locally in `data/wikidata_place_cache.sqlite`.
- Wikimedia reading lookups are cached locally in
  `data/wikimedia_reading_cache.sqlite`.
- The dictionary index is optional and rebuilt locally.
