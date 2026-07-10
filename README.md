# Wikipedia Sentence Reader

Local prototype for reading Japanese Wikipedia articles one sentence at a time.

## What It Does

- Accepts a Japanese Wikipedia article URL or title.
- Fetches article text through the MediaWiki API.
- Shows one sentence at a time.
- Tokenizes Japanese terms into canonical tokens.
- Adds readings, romaji, optional JMdict/JMnedict glosses, and hover-only phrase hints.
- Adds cached Wikimedia/Wikidata place annotations for likely place-name spans.
- Fills missing kanji readings from cached Japanese Wikipedia parenthetical readings
  when the source can be matched conservatively.
- Tracks session recognition choices in browser memory.

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

- Session/global persistence is in-memory only.
- Always-recognized state is in-memory only.
- Phrase matching is experimental and hover-only.
- Place annotations are generated from Japanese Wikipedia page hits with Wikidata IDs
  and are cached locally in `data/wikidata_place_cache.sqlite`.
- Wikimedia reading lookups are cached locally in
  `data/wikimedia_reading_cache.sqlite`.
- The dictionary index is optional and rebuilt locally.
