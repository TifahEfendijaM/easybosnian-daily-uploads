import json
import re
from datetime import datetime
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

from .core import ROOT, canonical


def instructional(card):
    if card["kind"] == "quiz":
        return [card["question"], *(o["text"] for o in card["options"])]
    return [card["body"], *([card["example"]] if card.get("example") else [])]


def public_text(package):
    parts = [package["caption"], *package["hashtags"]]
    parts.extend(c.get("alt_text", "") for c in package["cards"])
    parts.extend(" ".join([c.get("heading", ""), *instructional(c)]) for c in package["cards"] if c["kind"] != "quiz")
    return " ".join(parts)


def reservations(package):
    values = [("theme", key) for key in package["theme"]["equivalence_keys"]]
    values += [("word", key) for word in package["words"] for key in [word["lemma"], *word["equivalence_keys"]]]
    return sorted(set(f"{kind}:{canonical(key)}" for kind, key in values))


def validate(package, history=None):
    schema = json.loads((ROOT / "data/content.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(package)
    if [c["kind"] for c in package["cards"]] != ["quiz", "lesson", "word"]:
        raise ValueError("Cards must be quiz, lesson, word in that order")
    words = [canonical(w["lemma"]) for w in package["words"]]
    if len(set(words)) != 3:
        raise ValueError("Three different words are required")
    word_groups = [set(canonical(k) for k in [w["lemma"], *w["equivalence_keys"]]) for w in package["words"]]
    if any(word_groups[i] & word_groups[j] for i in range(3) for j in range(i)):
        raise ValueError("Words overlap through an alias or close variant")
    for c, w in zip(package["cards"], package["words"]):
        if canonical(c["word"]) != canonical(w["lemma"]):
            raise ValueError("Each card must use its assigned distinct word")
    quiz = package["cards"][0]
    if [o["label"] for o in quiz["options"]] != ["A", "B", "C"]:
        raise ValueError("Quiz markers must be A/B/C exactly once")
    if len(set(canonical(o["text"]) for o in quiz["options"])) != 3:
        raise ValueError("Quiz options must differ")
    if any(re.match(r"^[ABC][).:\s]", o["text"]) for o in quiz["options"]):
        raise ValueError("Option text must not duplicate its A/B/C marker")
    review = package["private_review"]
    correct = next(o["text"] for o in quiz["options"] if o["label"] == review["correct_option"])
    if canonical(correct) != canonical(review["correct_text"]):
        raise ValueError("Private correct_text must match the selected option")
    outside_quiz = canonical(public_text(package))
    banned = [review["correct_text"], *review["answer_aliases"], *review["identifying_hints"]]
    for answer in banned:
        if re.search(r"(?<!\w)" + re.escape(canonical(answer)) + r"(?!\w)", outside_quiz):
            raise ValueError("Quiz answer or identifying hint leaks into other cards, caption, hashtags or alt text")
    caption = canonical(package["caption"])
    if re.search(r"(?:odgovor|rjesenje|tacno|correct|answer)\s*(?:je\s*)?[abc](?!\w)", caption):
        raise ValueError("Public caption identifies an answer letter")
    # The selected word may be the correct option; it is metadata, never a quiz heading.
    if canonical(review["correct_text"]) in canonical(quiz["question"]):
        raise ValueError("Quiz question reveals the answer")
    palette = json.loads((ROOT / "data/design-palettes.json").read_text())[package["design_palette"]]
    for c in package["cards"]:
        if len(" ".join(instructional(c))) > 460:
            raise ValueError("Instructional copy is too long; rewrite rather than shrink indefinitely")
        prompt = c["background_prompt"].casefold()
        if "no text" not in prompt or "no logos" not in prompt or "no lettering" not in prompt:
            raise ValueError("Background prompts must forbid text, lettering and logos")
        for field in ("ink", "accent", "panel", "scrim"):
            if palette[field].casefold() not in prompt:
                raise ValueError("Prompt must explicitly describe every shared palette colour")
        if c["design_template"] not in prompt:
            raise ValueError("Prompt must be written for the chosen layout")
        if not any(w in prompt for w in ("uncluttered", "negative space")):
            raise ValueError("Prompt must reserve overlay space")
        if c["kind"] != "quiz" and canonical(c["heading"]) != canonical(c["word"]):
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
        own_date = package["date"]
        used = {k for b in history["batches"] if b["date"] != own_date for k in b["reservation_keys"]}
        if set(reservations(package)) & used:
            raise ValueError("Theme, word, alias or close variant repeats reserved/history content")
    return package
