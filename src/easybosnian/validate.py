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


def validate(package, history=None, include_today=False, require_website_footer=False, require_quiz_format=False, target_cefr=None, word_level_targets=None):
    schema = json.loads((ROOT / "data/content.schema.json").read_text())
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(package)
    except ValidationError as error:
        # Schema diagnostics must not echo the draft, private answers or model prose.
        path = '.'.join(str(part) for part in error.absolute_schema_path)
        raise ValueError(f'Content schema check failed at {path}; inspect the private draft') from None
    if [c["kind"] for c in package["cards"]] != ["quiz", "lesson", "word"]:
        raise ValueError("Cards must be quiz, lesson, word in that order")
    if target_cefr is not None and package.get('bosnian_level') != target_cefr:
        raise ValueError('New content must record the shared preparation difficulty')
    if word_level_targets is not None:
        for word, target in zip(package['words'],word_level_targets):
            if target is not None and word.get('bosnian_level') != target:
                raise ValueError('A regenerated or retained word does not match its required difficulty')
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
    if require_quiz_format and 'quiz_format' not in quiz:
        raise ValueError('New quiz content requires reviewed visual-identification or other format metadata')
    question = normalise(quiz["question"])
    # Catch the foreign-word translation template; the reviewer checks all public
    # copy for Bosnian correctness and the scene for relevance/semantic leakage.
    translation_action = re.search(r"\b(?:kaze|kazemo|reci|prevodi|prevesti|prijevod|prevod|znaci|rijec|naziv|translation|translate)\b", question)
    translation_language = re.search(r"\b(?:na bosanskom|na engleskom|englesk\w*|english)\b", question)
    if translation_action and translation_language:
        raise ValueError("Use a Bosnian description, situation or visual question instead of a foreign-word translation exercise")
    labels = [o["label"] for o in quiz["options"]]
    if labels not in (["A", "B"], ["A", "B", "C"], ["A", "B", "C", "D"]):
        raise ValueError("Quiz markers must be A/B, A/B/C or A/B/C/D exactly once")
    if len(set(normalise(o["text"]) for o in quiz["options"])) != len(quiz["options"]):
        raise ValueError("Quiz options must differ")
    if any(re.match(r"^[ABCD][).:\s]", o["text"]) for o in quiz["options"]):
        raise ValueError("Option text must not duplicate its option marker")
    review = package["private_review"]
    if review["correct_option"] not in labels:
        raise ValueError("Private correct_option must be one of the provided options")
    correct = next(o["text"] for o in quiz["options"] if o["label"] == review["correct_option"])
    if normalise(correct) != normalise(review["correct_text"]):
        raise ValueError("Private correct_text must match the selected option")
    outside_quiz = normalise(public_text(package))
    binary = len(quiz["options"]) == 2 and {normalise(o["text"]) for o in quiz["options"]} == {"da", "ne"}
    banned = [review["correct_text"], *review["answer_aliases"], *review["identifying_hints"]]
    for answer in banned:
        # Da/ne are ordinary Bosnian words, not identifying clues by themselves.
        if binary and normalise(answer) in {"da", "ne"}: continue
        if re.search(r"(?<!\w)" + re.escape(normalise(answer)) + r"(?!\w)", outside_quiz):
            raise ValueError("Quiz answer or identifying hint leaks into other cards, caption, hashtags or alt text")
    caption = normalise(package["caption"])
    if require_website_footer:
        lines = package['caption'].strip().splitlines()
        if (len(lines) < 2 or lines[-1] != '👉easybosnian.com'
                or not lines[-2].strip() or package['caption'].count('easybosnian.com') != 1):
            raise ValueError('New captions need a contextual Bosnian invitation followed by 👉easybosnian.com on the final line')
    if re.search(r"\b(?:mala ispravka|ispravka prethodn\w*|prethodn\w* objav\w*|(?:obrisan|izbrisan)\w* objav\w*|nova verzija objave)\b", caption):
        raise ValueError("Captions must stand alone without referring to corrections or deleted posts")
    if re.search(r"(?:odgovor|rjesenje|tacno|correct|answer)\s*(?:je\s*)?[abcd](?!\w)", caption):
        raise ValueError("Public caption identifies an answer letter")
    if binary and re.search(r"(?:odgovor|rjesenje|tacno|correct|answer)\s*(?:je\s*)?(?:da|ne)(?!\w)", outside_quiz):
        raise ValueError("Public text identifies the yes/no answer")
    # The selected word may be the correct option; it is metadata, never a quiz heading.
    if not binary and normalise(review["correct_text"]) in normalise(quiz["question"]):
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
        if c["kind"] == "word" and normalise(c["heading"]) != normalise(c["word"]):
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
        new_themes-=set(history.get('reused_theme_keys',[]));new_words-=set(history.get('reused_word_keys',[]))
        for day in history['days']:
            same=day.get('batch_id',day['content'].get('batch_id'))==package['batch_id'] if package.get('batch_id') else day['date']==package['date']
            if same and not include_today: continue
            old_themes,old_words=equivalents(day['content'])
            if new_themes & old_themes or new_words & old_words:
                raise ValueError('Theme, word, alias or close variant repeats history content')
    return package
