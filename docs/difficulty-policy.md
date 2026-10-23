# Difficulty, custom word selection and language

## Frozen level and editorial target

The wrapper freezes `selection.target_cefr/context.target_cefr` once before research. The workflow menu is random/A1/A2/B1/B2/C1/C2 for new, same_theme and newly selected custom words. Random probabilities are A1 50%, A2 25%, B1 12.5%, B2 6.25%, C1 3.125%, C2 3.125% (the remaining tail). Automatic 05:00 runs use random/new. Never redraw or read `data/preparation-settings.json`; the disabled `configure-level.yml` and legacy settings remain available for possible future use but have no publishing effect.

New/model-selected words use the frozen target. Compatible entered words receive their own researched individual level, not forced replacement to match the run. Retained words keep exact lemma/equivalence metadata and individual level; an older top-level bosnian_level may supply their old rating. If neither exists, keep null/unknown and their prior difficulty/style, without inheriting a newer target. same_words/same_images retain the source target (random only if absent) and ignore the new dropdown. Saved previews remain exact.

CEFR is an editorial target, not an official Bosnian word-rating list:

| Level | Content |
|---|---|
| A1 | familiar concrete words, very short direct sentences/simple examples |
| A2 | everyday activities/routines, short linked descriptions |
| B1 | practical/cultural situations, connected accessible explanations |
| B2 | broader concrete/abstract vocabulary, nuanced contrasts, idiomatic examples |
| C1 | precise vocabulary, implied meaning, sophisticated usage |
| C2 | fine distinctions and flexible idiom without forced obscurity |

Assess a Znaš li? comparison/topic by its complete lesson/taught terms, not only its internal seed. Keep every level readable within copy/fit limits; advanced levels do not permit grammar lists, ambiguity or invented facts. Review suitability/replacements privately. Reference: https://www.coe.int/en/web/common-European-framework-reference-languages/table-1-cefr-3.3-common-reference-levels-global-scale .

## Custom actions and corrections

Actions apply independently in quiz/lesson/word order. Blank theme retains the selected batch's theme. There is no original-morning snapshot.

| word_action | Meaning |
|---|---|
| keep_today | keep selected word/metadata and write fresh content/photo/design; a changed theme makes the wrapper delegate it to chatgpt |
| chatgpt | choose a semantically new distinct seed at target_cefr |
| entered | research the matching text field, assess its individual level and write fresh content |
| same_image | keep word/metadata/original photo/exact prompt; write fresh copy/design |
| same_image&design | keep the complete word/card, original photo and exact feed/Story JPEGs; see preparation-task.md and element-design-recovery.md |

All actions except entered require empty matching text fields. same_image actions remain pinned even after a theme change; incompatible retained content blocks rather than being replaced. Without a complete source, a custom theme is required and words must be entered or delegated. The wrapper delegates structurally unusable seeds (empty entered input, absent keep_today source, over-180-character/non-word-only input, duplicate exact normalized seed after its first occurrence); `word_input_fallbacks` records indices/causes and resulting null requested_words/chatgpt slots. Nonempty text paired with a non-entered action, invalid actions or unusable themes are configuration errors.

Research intended spelling FIRST for entered/kept seeds. Preserve an unambiguous valid thematic correction (for example Cijenkati se → cjenkati se), rebuild equivalents and assess its own level; record cause=spelling_correction. A different run target or historical repetition is not an error. If the seed cannot be established/validated or fails theme-fit, Bosnian validity, within-batch distinctness or usability, replace ONLY that slot with a suitable new target-level seed. Lesson replacements may be comparisons/topics. Preserve other valid slots.

Record each correction/fallback in `private_review.word_replacements`: zero-based word_index, exact requested_word, actual chosen_word, researched reason of 20–400 characters, cause=spelling_correction/theme_mismatch/invalid_bosnian/word_overlap/unusable_seed. Match the entered/keep_today request; already-delegated slots need no replacement review. New reviews require cause and never history_repeat. Historical entered reviews lacking cause retain theme_mismatch meaning; old history_repeat records remain readable, not newly valid.

Manual themes/entered/kept words and spelling corrections may repeat ANY history. Only delegated choices and genuinely different fallback seeds require full-history novelty; use `novelty_history` with the final package. All theme-fit, distinctness, language, research, secrecy and fit checks still apply. Correct the same unreviewed draft/execution, rebuild affected metadata/copy/scenes/caption/quiz reviews, and rerun all validators. Selection corrections waive no unrelated failure and authorize no workflow/model/publication restart. Source research establishes linguistic truth; deterministic checks validate its recorded structure.

## Field languages and caption level

| Field | A1/A2 individual word/lesson | B1–C2 or unknown legacy individual level |
|---|---|---|
| lesson/word card.body | natural English, body_language=en | standard Bosnian, body_language=bs |
| quiz question | natural English, question_language=en | standard Bosnian, question_language=bs |
| featured word, heading, options (including Da/Ne), examples, hashtags, alt text | Bosnian | Bosnian |

An English question may describe a meaning/situation or ask what is pictured; do not ask for foreign-word translation, include the correct Bosnian answer/letter or leak hints through another card. Preserve exact question/options across feed/Story/poll handling; renderers never translate. Internal scene prompts/research/equivalence metadata may be English. Review English accuracy AND every Bosnian field before setting `private_review.language_policy_checked=true`.

Determine caption language with `caption_language(package)` and `caption_levels(package)`: English when no known B1–C2 content exists and the highest returned level is A1/A2; otherwise Bosnian. Mixed A1/A2 is English; any known higher-level content makes it Bosnian. Unknown legacy ratings remain null; use the existing target-audience fallback without inventing ratings. Set package.caption_language=en/bs. Retained-word reruns follow actual retained levels, not a different dropdown; saved previews are unchanged.

Weave the actual shared level or ONLY lowest/highest mixed-level endpoints into a natural theme-connected caption sentence, not a standalone label. With unknown retained ratings, address the configured target audience without claiming a rating. Example phrasing is optional, not a fixed slogan. Review accuracy/secrecy and preserve caption limits and the website ending specified in preparation-task.md. Fresh validation requires caption-level/language checks; saved history is not rewritten.
