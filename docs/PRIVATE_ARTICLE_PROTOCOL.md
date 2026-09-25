# Private Article → Review Deck Protocol

This is the repeatable workflow for a Japanese article that you lawfully access
and keep for private study. It deliberately keeps the downloaded source,
extracted text, vocabulary overrides, and generated article outside Git.

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

Every distinct token from every viewed sentence is included at End Session.
The final state has this deterministic Anki meaning:

Unmarked occurrences count as unrecognized. Repeated occurrences of the same
canonical token are combined before scheduling.

| Reader result | Anki answer | Effect |
| --- | --- | --- |
| unrecognized is greater than or equal to recognized | Again (`1`) | enters review/relearning at highest priority |
| recognized is greater than unrecognized | Good (`3`) | due in `recognized - unrecognized` days |
| always recognized | Easy (`4`) | longest standard answer delay |

For a recognized majority, the positive difference is the priority margin. A
1-vote margin is due in 1 day; a 5-vote margin is due in 5 days. This keeps
borderline vocabulary ahead of consistently recognized vocabulary. A tie is
handled conservatively as Again.

If a token is absent from the deck, its note is created. If its card is New or
in a learning queue, it is first promoted to Review. The answer is then applied
through Anki's scheduler. Consequently the deck contains no New cards after a
successful sync; Again cards may correctly enter Anki's *relearning* queue.

The note front is the canonical Japanese expression. Reveal shows hiragana,
romaji, English meaning, observed surface, source sentence, article link, and
dictionary identity.

## 6. End only after a successful sync

End Session checks every token for the required reading and translation, then
creates or updates the notes and applies Again/Good/Easy. The local reader is
reset only after all operations succeed. If Anki or AnkiConnect is unavailable,
the session remains open so it can be retried without losing marks.

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
