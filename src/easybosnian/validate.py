import json
import re
from datetime import datetime
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from .core import ROOT
import unicodedata


def instructional(card):
    if card["kind"] == "quiz":
        return [card["question"], *(o["text"] for o in card["options"])]
    return [card["body"], *([card["example"]] if card.get("example") else [])]


def public_text(package):
    parts = [package["caption"], *package["hashtags"]]
    if any(c.get("example") for c in package["cards"]): parts.append("PRIMJER")
    parts.extend(c.get("alt_text", "") for c in package["cards"])
    parts.extend(" ".join([c.get("heading", ""), *instructional(c)]) for c in package["cards"] if c["kind"] != "quiz")
    return " ".join(parts)


def normalise(text):
    # Text comparison for validation only, never a generated reservation/database key.
    text=unicodedata.normalize('NFKD',text.casefold().replace('đ','d'))
    return ' '.join(re.sub(r'[^a-z0-9 ]',' ',''.join(c for c in text if not unicodedata.combining(c))).split())


def equivalents(package):
    themes={normalise(k) for k in [package['theme']['name'],*package['theme']['equivalence_keys']]}
    words={normalise(k) for w in package['words'] for k in [w['lemma'],*w['equivalence_keys']]}
    return themes,words


def validate(package, history=None, include_today=False):
    schema = json.loads((ROOT / "data/content.schema.json").read_text())
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(package)
    except ValidationError as error:
        # Schema diagnostics must not echo the draft, private answers or model prose.
        path = '.'.join(str(part) for part in error.absolute_schema_path)
        raise ValueError(f'Content schema check failed at {path}; inspect the private draft') from None
    if [c["kind"] for c in package["cards"]] != ["quiz", "lesson", "word"]:
        raise ValueError("Cards must be quiz, lesson, word in that order")
    words = [normalise(w["lemma"]) for w in package["words"]]
    if len(set(words)) != 3:
        raise ValueError("Three different words are required")
    word_groups = [set(normalise(k) for k in [w["lemma"], *w["equivalence_keys"]]) for w in package["words"]]
    if any(word_groups[i] & word_groups[j] for i in range(3) for j in range(i)):
        raise ValueError("Words overlap through an alias or close variant")
    for c, w in zip(package["cards"], package["words"]):
        if normalise(c["word"]) != normalise(w["lemma"]):
            raise ValueError("Each card must use its assigned distinct word")
    quiz = package["cards"][0]
    if [o["label"] for o in quiz["options"]] != ["A", "B", "C"]:
        raise ValueError("Quiz markers must be A/B/C exactly once")
    if len(set(normalise(o["text"]) for o in quiz["options"])) != 3:
        raise ValueError("Quiz options must differ")
    if any(re.match(r"^[ABC][).:\s]", o["text"]) for o in quiz["options"]):
        raise ValueError("Option text must not duplicate its A/B/C marker")
    review = package["private_review"]
    correct = next(o["text"] for o in quiz["options"] if o["label"] == review["correct_option"])
    if normalise(correct) != normalise(review["correct_text"]):
        raise ValueError("Private correct_text must match the selected option")
    outside_quiz = normalise(public_text(package))
    banned = [review["correct_text"], *review["answer_aliases"], *review["identifying_hints"]]
    for answer in banned:
        if re.search(r"(?<!\w)" + re.escape(normalise(answer)) + r"(?!\w)", outside_quiz):
            raise ValueError("Quiz answer or identifying hint leaks into other cards, caption, hashtags or alt text")
    caption = normalise(package["caption"])
    if re.search(r"(?:odgovor|rjesenje|tacno|correct|answer)\s*(?:je\s*)?[abc](?!\w)", caption):
        raise ValueError("Public caption identifies an answer letter")
    # The selected word may be the correct option; it is metadata, never a quiz heading.
    if normalise(review["correct_text"]) in normalise(quiz["question"]):
        raise ValueError("Quiz question reveals the answer")
    for c in package["cards"]:
        if len(" ".join(instructional(c))) > 460:
            raise ValueError("Instructional copy is too long; rewrite rather than shrink indefinitely")
        prompt = c["background_prompt"].casefold()
        if "no text" not in prompt or "no logos" not in prompt or "no lettering" not in prompt:
            raise ValueError("Background prompts must forbid text, lettering and logos")
        # Palette/layout IDs are validated by the schema and used by Pillow.
        # FLUX needs a natural scene description, without renderer vocabulary.
        # Actual glyph wrapping and semantic editorial review remain mandatory.
        if c["kind"] != "quiz" and normalise(c["heading"]) != normalise(c["word"]):
            raise ValueError("Featured heading must be the reviewed word")
        for text in instructional(c):
            if "\n" in text or any(ord(x) < 32 for x in text):
                raise ValueError("Unexpected control characters")
    if not all(review[flag] for flag in ("standard_bosnian_checked", "sources_checked", "semantic_history_checked", "no_answer_leak_checked")):
        raise ValueError("A required editorial check is incomplete")
    if datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("Review time must have a timezone")
    for s in package["sources"]:
        if urlparse(s["url"]).scheme != "https":
            raise ValueError("Sources require HTTPS")
    if history:
        new_themes,new_words=equivalents(package)
        for day in history['days']:
            if day['date']==package['date'] and not include_today: continue
            old_themes,old_words=equivalents(day['content'])
            if new_themes & old_themes or new_words & old_words:
                raise ValueError('Theme, word, alias or close variant repeats history content')
    return package
