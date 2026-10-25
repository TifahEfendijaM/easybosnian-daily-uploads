# Research and content preparation

This is the content policy for the research child, invoked through `cloud-agent-task.md`. Difficulty, per-word selection/correction and language rules are authoritative in `difficulty-policy.md`. Post-photo composition belongs to the visual reviewer and `visual-style-contract.md`, not this stage.

## 1. Trusted input and selection

Read the complete private history research view and selection through the bounded page reader in `cloud-agent-task.md`, including every retained/imported row and the complete selected previous package. The original `build/preparation-context.json` remains authoritative for local validation and optional full-detail reads. Set `package.batch_id=context['batch']['batch_id']` and `package.date=context['batch']['date']`. Review timestamps reflect the actual review now, even when replacing an older content date. Metadata-only `legacy_word_history` imports count for novelty; their dates/themes may be estimated/inferred. Never invent their missing text/sources/reviews or use them as renderable packages.

| content_selection | Preserve | Research afresh |
|---|---|---|
| new | trusted identity/date/target level | semantically new theme, quiz/word lemmas, distinct lesson seed, all copy/captions/scenes |
| same_theme | exact previous theme metadata | new words/seed and all copy/captions/scenes |
| same_words | exact theme, words/roles, equivalents and individual levels | instructional copy, quiz, caption/hashtags/alt text, scene prompts and reviews |
| same_images | same_words metadata plus exact original photos/background_prompt strings | all instructional copy, quiz, captions and reviews suited to the attached photos |
| custom | trusted requested_theme/requested_words and pinned metadata | content for selected actions under difficulty-policy.md |

Saved-content previews reuse exact content; fresh private previews follow the same research checks without saving history. Full same_images ignores custom fields. Other modes must not copy unchecked/stale private reviews. The wrapper's latest/none/all_today target determines storage/cleanup, not permission to bypass novelty or change the frozen identity.

In custom mode, inspect attached retained photos in `reused_photo_kinds` order and keep their prompts unchanged. `same_image` retains a role's word/metadata/photo but researches fresh copy/design. `same_image&design` freezes the COMPLETE previous `cards[index]` and `words[index]` objects: no changed copy, prompt or design. A frozen quiz also keeps its exact private answer/research fields and option count (the supplied quiz_option_target). Research remaining cards and a fresh caption; verify secrecy/language/level/fit across the combined batch. Incompatible frozen content must block, not be silently replaced. Model drafts omit `rendered_sources`, `background_source` and `background_sources`; the parent verifies unchanged bytes and seals those references.

## 2. Selection-aware novelty

Generated NEW themes must differ semantically from EVERY retained published batch, including imports, independent same-date rows and the selected source. Read names, aliases, equivalents AND previous card content. A renamed theme, different words/CEFR level or minor variation of the same scenario/activity is not new. Avoid closely related revisits; choose a clearly distinct scenario rather than repeatedly returning to familiar settings. Research stable theme equivalents, without overly generic keys such as people/home/outdoors for unrelated themes.

For model-selected words/lesson seeds, check aliases, inflections, translations, synonyms, diminutives, close variants and stable semantic equivalents against all rows. Store stable English concept equivalents and Bosnian aliases in metadata. Compare normalized text for validation only, never to generate reservation keys. Compare full lesson content for repeated comparisons/topics, not just its anchor. Keep two different Bosnian quiz/word lemmas and a distinct lesson seed. For comparison/topic seeds include principal taught Bosnian lemmas and stable concept equivalents as novelty terms, without claiming they are synonyms.

Explicit custom themes and entered/kept words, retained selections and researched spelling corrections may intentionally repeat ANY history. Do not reject/replace them solely for repetition or label them novel. Only delegated/null slots and genuinely different fallback choices must be new. Use `novelty_history` with the FINAL checked package, not a batch-wide novelty waiver. Set `semantic_history_checked` only after this selection-aware review. Removed/replaced rows no longer reserve their themes; existing rows remain authoritative until the wrapper's confirmed-publication save. No reservation/database keys are generated.

## 3. Sources and exact copy

Open reliable HTTPS sources for spelling, meanings, distinctions and factual claims, preferably Bosnian institutes and Senahid Halilović's Pravopis. Croatian/Serbian references may corroborate shared meanings, not determine Bosnian spelling. Record relevant entry URLs and what they verify. Write original learner-friendly prose; never invent sources, entertaining facts or unchecked review flags.

Produce exactly three cards in quiz/lesson/word order. Preserve standard Bosnian and č, ć, š, ž, đ in all Bosnian fields. Follow the per-field English/Bosnian rules in difficulty-policy.md. Instructional copy must fit the 460-character maximum and actual measured feed/Story layouts; do not truncate, silently translate or remove diacritics. Category labels/PRIMJER are supplied by Pillow: do not repeat PRIMJER in the example sentence. Keep headings within the measured two-line limit and provide 3–5 appropriate hashtags and accurate alt text without answer leakage.

## 4. Quiz and answer secrecy

Pitanje dana may test practical situations, everyday/cultural facts, meaning/usage, comparisons or visual naming. Use one objectively correct answer, plausible researched distractors and distinct Bosnian choices labelled A/B, A/B/C or A/B/C/D. Questions follow the quiz word's individual language/level; never ask for translation of a foreign word. Privately justify the correct answer and why each distractor is wrong.

For each fresh quiz the wrapper independently draws `selection.quiz_format_target`: visual_identification with probability 25%, other with probability 75%. Use that exact format, not a model preference, redrawing, or a history-balancing quota. Research an appropriate question for the selected theme/retained photo and format; if impossible report blocked rather than silently switching. An explicitly frozen same_image&design quiz retains its existing format without a draw. Saved-content previews also retain their content. The centred complete-photo feed template is mandatory ONLY for visual_identification and ruled out for other quiz types. This format draw is independent of answer count and difficulty.

For each fresh research attempt the wrapper draws `selection.quiz_option_target` uniformly from 2/3/4 (one-third each). Use that exact count for a non-binary quiz: no redraw, history balancing, convenience override or preference for four. A genuinely binary question has exactly two mutually exclusive possibilities and uses two, regardless of target; ordinary multiple choice is not binary. Record `private_review.quiz_choice_review={target: supplied integer, binary: true/false, reason: researched explanation of 20–400 characters}`. If the target cannot yield a sound quiz for the retained theme/photo, choose another suitable question or report blocked; never pad weak distractors. A frozen quiz keeps its reviewed count. Saved older content without the review stays readable. The visual stage cannot change choices/count.

Decide the tested unknown BEFORE drafting its scene. A visual-naming photo shows one unmistakable referent: seeing it is the question, not a leak. If the question already names a subject, its photo may show that subject. For hidden identities/facts, use relevant context that does not solve the unknown; never substitute an unrelated room/wall/landscape merely to avoid clues. No written answer, correct letter, ticks or comparison of the choices in the photo.

Keep answer letters/text/aliases, paraphrased answer explanations and identifying hints out of public captions, hashtags, alt text and other cards, including English explanations. Visual-naming alt text describes the task without naming its target. Privately review scene relevance and what it gives away. `quiz_format="visual_identification"` means actual picture-identification/naming; use `"other"` for every other fresh quiz, including yes/no/fact questions that mention a picture. Review the classification rather than infer it mechanically from a phrase.

## 5. Lesson and word

Znaš li? is a useful mini-situation, practical tip, verified everyday/cultural fact or meaningful word comparison, beyond a dictionary definition. Its internal `words[1].lemma/card.word` may be an anchor, comparison or short Bosnian topic. Honour an entered seed's meaning; do not force a one-word template. Give the public lesson a concise natural Bosnian heading describing its actual point, independently of that seed. Research every distinction/claim, especially origins/culture. Avoid routine conjugation/declension lists, isolated spelling drills and grammar trivia. Use a natural example when useful. The background illustrates the actual lesson/comparison/activity, not merely the anchor. Vary ideas/scenes naturally while respecting full-history novelty and quiz secrecy.

Riječ dana gives a short, natural theme-relevant definition and Bosnian example sentence. Both lesson and word copy suit their individual reviewed level, including beginner English bodies; featured words/headings/examples remain Bosnian.

## 6. Natural photographs and fallback palette

Write concise natural English FLUX scene prompts, usually 30–60 words. Begin `Photorealistic photograph of…` or `Photorealistic macro photograph of…`; describe relevant real subjects/actions/environment, natural light/mood, realistic textures/proportions and true-to-life colours. End exactly `No text, no lettering, no logos.` No illustration, cartoon, diagram, stylised CGI, 3D rendering or abstract shapes.

Leave composition to FLUX. Do not direct subject position, camera framing, negative space, headroom, empty areas or top/middle/bottom space for overlays. Never shape a photo from measured copy or guessed text placement. No coordinates, dimensions, hex codes, template IDs, panels/boxes, headings, quiz-option/UI descriptions or logo placement. Ordinary scene colour names are allowed only when natural to the subject; no palette-driven recolouring, colour wash, artificial coloured lighting or forced accents on clothes/furniture/books. Retained-photo prompts stay EXACTLY unchanged.

After drafting scenes, compare EVERY approved palette in `data/design-palettes.json` and choose one shared fallback `design_palette` whose ink/paper/accent complements the planned natural materials, light and theme with readable contrast. Catalogue order is not a ranking: no first/last/familiar shortcut, random selection or mechanical rotation. Explain the fit privately in `private_review.notes`, alongside scene relevance and quiz review. This is scene-based fallback planning, not a claim to have inspected new photographs. Final independent per-image palettes/styles/placement are selected AFTER generation by the visual reviewer. Omit design_template; never select old preparation-time layouts.

## 7. Standalone captions

Write a fresh natural caption about this batch in the language determined by difficulty-policy.md, weaving in the actual shared level or mixed-level endpoints. Never mention prior/deleted/replaced content, reruns, corrections, “mala ispravka” or a “new version”; previous content is private selection context. Preserve quiz secrecy and existing caption limits.

End with one or two fresh natural sentences connecting the theme/situation/non-answer words to learning Bosnian on EasyBosnian, inviting registration or continued learning, then `👉easybosnian.com` exactly once on the FINAL line, with no space after the arrow. No separate 👇 line, fixed generic slogan or recycled invitation. Free lessons/registration may be mentioned; do not promise an unchecked specific lesson/vocabulary pack. Review the contextual connection and secrecy privately. Fresh preparation requires the footer; saved history/previews are not rewritten to add it.

## 8. Fit and handoff

Use `data/content.schema.json` and the exact validation sequence in cloud-agent-task.md. Deterministic baseline body density is 44px/38px padding through 160 characters, 38px/30px through 240, then 34px/24px; real glyph/line/label measurements decide fit. These copy-fit measurements must NEVER become FLUX framing instructions. Correct the unreviewed draft and rerun all checks rather than bypass or truncate.

All Stories use treatment B at 1080×1920: complete original photo in its own section, exact explanations/answers on separate panels and any unboxed Lora Italic PRIMJER on the paper footer with an accent separator. Every quiz Story orders question → photo → choices. Visual-identification feed quizzes also use treatment B at 1080×1350; other feed cards receive post-photo review. Preserve complete photos without stretch/crop in treatment B, measured readability/photo space and exact reviewed question/options across feed, Story and native-poll caption handling. Existing legacy quiz-format omissions retain their saved feed behavior. See `story_layouts.py`/`render.py` only as needed for fit.

The child stops after a validated private draft and structured completion. The wrapper independently validates/stages it, persists cloud credentials, inspects photos and reviews/renders designs. No draft or failed generation consumes history; only confirmed feed publication saves it. Operational scheduling/cleanup/reporting instructions are for the wrapper, in pipeline-operations.md.
