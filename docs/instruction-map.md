# Instruction ownership and cleanup review

This maintainer map records the instruction-only consolidation from main commit `5fbbf2f`. It is NOT additional model input. Current requirements have one policy owner; runtime prompts include the relevant stage rules and exact data. The immutable master prompt is historical, not an additional conflicting runtime rulebook. Dated implementation notes in other operational references do not override the current policies indexed in AGENTS.md.

## Preserved requirements

| Requirement group | Current owner | Existing verification |
|---|---|---|
| Exact private repository, guarded Git/GitHub, no other chat/session state | AGENTS: Scope | core repository guard; cloud diagnostics tests |
| Free services, no paid fallback/new infrastructure, original master/logo immutable | AGENTS: Invariants; pipeline-operations: Artwork | project/image_hosting tests; byte comparison in cleanup audit |
| Stage-specific credentials/tools/write boundaries and structured completion | cloud-agent-task; pipeline-operations: Scheduling | cloud_preparation, codex_diagnostics, photo_quality tests |
| Exactly three ordered quiz/lesson/word cards, sourced original prose/diacritics, no unchecked flags | preparation-task: Sources | project, lesson_topics, run_difficulty_language tests |
| Opened Bosnian sources; corroboration limits; claims/meanings/aliases | preparation-task: Sources/Novelty | existing editorial/schema validation plus source review |
| Frozen batch identity/date, legacy metadata/imports, selected source | preparation-task: Trusted input; pipeline-operations: Frozen batches | batch_targets, multiple_batches, migration tests |
| new/same_theme/same_words/same_images/custom selection and exact pins | preparation-task: Trusted input; difficulty-policy: Custom actions | replacement, custom_history_reuse, photo_reuse tests |
| Entire same_image&design card/word, frozen quiz review/count, exact JPEG snapshots | preparation-task: Trusted input; element-design-recovery: Exact finished cards | frozen_cards tests |
| Full semantic history, synonyms/inflections/concepts, close themes and comparisons; manual-repeat exceptions | preparation-task: Novelty | project, custom_history_reuse, lesson_topics tests |
| Weighted frozen CEFR, retained/unknown individual levels, disabled old workflow | difficulty-policy: Frozen level | levels, run_difficulty_language tests |
| Custom action empty fields/theme changes, structural delegation, spelling-first and slot-only corrections | difficulty-policy: Custom actions | custom_word_fallback, custom_same_image tests |
| Correction review fields/causes; no history_repeat for new reviews; legacy compatibility | difficulty-policy: Custom actions | custom_word_fallback, levels tests |
| English beginner body/questions/captions, Bosnian words/options/headings/examples, retained-level caption semantics | difficulty-policy: Field languages | run_difficulty_language and english_captions tests |
| Quiz variety/relevance/hidden-unknown secrecy, private distractor justification and naming classification | preparation-task: Quiz | project tests plus source-opening review |
| Uniform 2/3/4 target; genuine binary exception; frozen quiz count; no visual-stage choice changes | preparation-task: Quiz | quiz_choice_count, frozen_cards tests |
| Lesson topic/comparison flexibility, internal seed versus public heading, meaningful reviewed lesson | preparation-task: Lesson | lesson_topics tests |
| 460-character exact copy, density thresholds, real feed/Story fit, no truncation | preparation-task: Sources/Fit | project, visual_contract, visual_acceptance tests |
| Natural scene-only FLUX prompt/start/end, no composition/recolouring, scene-first fallback palette | preparation-task: Photographs | project prompt validation; cloud_preparation tests |
| Standalone contextual captions, level mention, fresh invitation and exact final website line, 3–5 hashtags | preparation-task: Captions; difficulty-policy: Caption level | caption_levels, english_captions, project tests |
| Full-photo/crop-only visual inputs, no styled refs, no answer key, fallback-only default_plan | visual-style-contract: Inputs; runtime visual prompt | visual_placement, visual_outcomes tests |
| Full catalogue consideration; recent accepted metadata only; no first/last/familiar shortcut | visual-style-contract: Inputs | fixed_fades, visual_outcomes tests |
| Independent per-photo palette; all-palette rolling two-in-nine/second-in-batch exception, fallback observations count | visual-style-contract: Inputs | neutral_titles_palette_variety, title_palette_limits tests |
| All 14 body/15 answer/6 category/4 badge treatments; independent panel/badge and coherent mixtures | visual-style-contract: Treatments/Categories; unchanged live registries | visual_contract, visual_refinements, oct22_visual_rules tests |
| Approved role/typography/window fields; no arbitrary code/colours/fonts/CSS/filters/manual breaks | visual-style-contract: Declarative fields | visual_contract, fixed_fades, visual_placement tests |
| Fixed 100% fresh body/answer panels; palette-role text/surface combinations; legacy opacity readable | visual-style-contract: Categories | panel_opacity, fixed_fades tests |
| No category shades; bounded chip alternative, actual accents/contrast, protected category strip | visual-style-contract: Categories | category_no_fades, visual_refinements tests |
| Neutral title backing/palette text; standard/defined equally considered for either backing | visual-style-contract: Title | oct22_visual_rules, neutral_titles_palette_variety tests |
| Separate unboxed Lora Italic examples; neutral/palette-coloured pairs; standard/sharp model choice | visual-style-contract: PRIMJER | oct22_visual_rules, fixed_fades tests |
| Gentle adaptive title presets, weaker white surround, lower example padding, combined shade weight | visual-style-contract: Title/PRIMJER | fixed_fades, oct22_visual_rules tests |
| Free independent body/example/answer positioning, no adjacency/max gap; shared rows and intentional grids | visual-style-contract: Placement/Answers | visual_acceptance, visual_placement tests |
| Full-photo strong default/middle-window exception, editorial order, contained visual quizzes | visual-style-contract: Inputs/Geometry | visual_contract, visual_placement tests |
| Exact glyph wrapping/leading/collision/coverage/contrast, measured profiles retain all creative choices | visual-style-contract: Typography/Geometry | visual_acceptance, visual_contract tests |
| One-line example widening and nearest-safe translations preserve other accepted fields | visual-style-contract: Placement; element-design-recovery | example_line_title_fade, design_repair tests |
| Photo defect versus normal occlusion/crop; max three, best-rated selection/tie, retained-photo exceptions | element-design-recovery | photo_quality tests |
| Max three design proposals; locked accepted elements; smallest failed set/nearest safe recovery | element-design-recovery | element_recovery tests |
| Independent palette/layout provenance; partial recovery, fixed rejection reasons, no unsafe final fallback | visual-style-contract: Recovery; element-design-recovery | visual_provenance, visual_outcomes, element_recovery tests |
| Unchanged treatment-B Stories, complete photo/order, exact copy and feed palette/category reuse | preparation-task: Fit; visual-style-contract: Compatibility | story_layouts/project, visual_refinements tests |
| 05:00 Sarajevo/DST dispatch, kill switches, exactly three modes, no catch-up/monitor/retry | pipeline-operations: Scheduling | external_trigger, batch_targets, project tests; Worker suite |
| Published-only history, partial success and failed-save behavior, latest/none/all_today | pipeline-operations: History | published_history, all_today, multiple_batches tests; Worker suite |
| Private cache provenance/expiry/byte proofs, eventual consistency exposure and read-only polling | pipeline-operations: Artwork; element-design-recovery | photo_reuse, frozen_cards, image_hosting tests; Worker suite |
| Independent publishing/account/token checks and credential persistence | pipeline-operations: Scheduling/Publishing | daily/facebook_stories, cloud_preparation tests |
| Batch-specific cleanup, complete ownership listing/confirmation, unsupported deletion exclusions | pipeline-operations: Cleanup | cleanup_diagnostics and all_today tests |
| Parent-only exact native poll, omission on limits, status/readback without republish | pipeline-operations: Poll; instagram-polls | instagram_polls tests |
| Story quota preflight/numeric refusal, counter conflicts, deletion-code distinction | pipeline-operations: Quotas; failures | instagram_quota and cleanup_diagnostics tests |
| Safe diagnostics/issues; exact-run reports/provenance/prompts; GitHub-only/no missing-start alert | pipeline-operations: Reporting | codex_diagnostics, flux_errors, success_report tests |
| Reviewed branch/diff/deployment order, no extra live test or replayed historical migrations | AGENTS: Development; pipeline-operations: Rollout | guarded review; migration-and-rollout historical reference |

## Superseded wording removed from active instructions

- One visual call/whole-layout fallback → bounded defect/rejection proposals and element-scoped recovery; service/API/publication errors still receive no retry.
- Fixed-sharp or random PRIMJER, fixed-white title edges → current photo-assessed choices, with the exact original preset catalogues retained.
- Unconditional Bosnian quiz/caption prose → existing individual-level and actual-batch-level language policy.
- Shared final palette or “never choose a slightly less optimal repeat alternative” → independent per-photo choice subject to the existing all-palette alternatives-first exception.
- Repeated opacity history, migration/deployment recipes and chronological refinements → one current rule plus legacy/operational reference.

No catalogue, schema, measurements, renderer, fallback/recovery algorithm, probability, source identity, credential, scheduling, history, cleanup or publisher implementation is changed. The photographic-quality prompt and recovery policy remain unchanged. Tests and the cleanup audit verify that only the initial visual instruction prose changed in executable Python; its catalogue/context serialization is retained.
