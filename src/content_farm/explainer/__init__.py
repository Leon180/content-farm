"""Explainer (slide-deck) video line.

``deck.json`` is the single source of truth: it is validated by
:mod:`content_farm.explainer.deck`, converted to the shared ``script.json``
contract by :mod:`content_farm.explainer.to_script`, rendered to PNG slides by
:mod:`content_farm.explainer.render`, and placed on the assembly timeline by
:mod:`content_farm.explainer.timeline`. Nothing downstream of voice needs to
know that the video is a slide deck.
"""
