# Cryptoole

**未解決暗号のオープン検索エンジン** / an open search engine for unsolved historical ciphers

https://cryptoole.satoru.net/

Cryptoole brings the lists of unsolved (and recently solved) historical ciphers published on several sites into one
searchable index: Cryptiana, cyphersolver, CryptoCellar, DECODE and cipher-readings. Only titles, dates, shelfmarks,
statuses, page counts and links are taken; every record links back to its source.

## What is here

| File | What it does |
|---|---|
| `udb.py` | Imports the sources into SQLite, groups series, assigns the unified IDs and builds the static site (`index.html`, `idx.json`, `c/*.json`). `python3 udb.py import` / `python3 udb.py build` |
| `attrs.py` | Country, language, cipher system, symbols, people and relations for each record |
| `seriespage.py` | The detail page of every record or series (`case.html`) |
| `statspage.py` | Decipherment statistics (`stats.html`) |
| `specpage.py`, `ID-SPEC.md` | The unified format: IDs, series, dates, solution records (`spec.html`) |
| `apidoc.py`, `api.cgi` | The public read-only JSON API and its documentation (`api.html`) |
| `decode_fetch.py` | Reads DECODE's public record list and record views |
| `ogimage.py`, `sidemenu.py` | Card image and shared header / menu |
| `data/attributes.csv`, `data/relations.csv` | Hand-checked attributes and relations between ciphers — **contributions welcome** |
| `data/image-rights.md` | Survey of archives' image reuse terms (for thumbnails) |

## Unified IDs

Every record gets a permanent ID such as `FR1591-3` (country of origin + year + serial; `XX` / `X` when unknown), and
every series an ID such as `CS00042`. IDs never change once given. The sources' own numbers (DECODE `R1876`,
cyphersolver `#152`, …) are kept beside them. See `ID-SPEC.md`.

## Running it

This code runs inside the satoru.net crypt site and reads a few files from its sibling folders
(`../tomokiyo/`, `../bourdeau/` — fetched source data — and `../timeline/index.html`, `../bourdeau/index.html` for the
shared header and styles). It needs Python 3, `markdown`, and `playwright` (only for `ogimage.py`).

## Contributing

Corrections are welcome as issues or pull requests — especially to `data/attributes.csv` (country, language, system,
people, keywords for a record) and `data/relations.csv` (ciphers that share a key, answer each other, or are the same
cipher). Please cite your evidence in the `note` column.

## License

Code and specification: MIT (see `LICENSE`). Icons: see `NOTICE.md`. The records belong to their sources.
