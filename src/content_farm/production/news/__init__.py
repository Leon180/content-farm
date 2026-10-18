"""HN 中文版: daily Shorts + a weekly long video on the chipcat channel.

Free sources only (HN official API, Lobsters RSS, arXiv API); every story is
read at its original URL (or arXiv abstract) before a script is written.

- :mod:`.fetch`    sources + polite HTTP (per-host spacing, arXiv 3 s)
- :mod:`.rank`     dedupe, freshness window, Taiwan relevance, score
- :mod:`.verify`   read the original page; record URL + read time
- :mod:`.review`   mobile candidate page (Leon picks)
- :mod:`.script`   ``news_script.json`` (hook → what → why → analogy → take) + lint
- :mod:`.render`   9:16 pages with the chipcat mascot → ``assembly/final.mp4``
- :mod:`.weekly`   pick the week's 3–5 most important Shorts → weekly plan
- :mod:`.daily`    the ``produce.py news daily|weekly`` orchestration
"""
