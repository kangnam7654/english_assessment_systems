# Rubric evidence

[한국어](README.md) · [Final grade rubrics](../../criteria/README.en.md)

This folder contains the sources and reconstruction record for `project-writing-v1`.
Use the finalized files in `criteria/grades/` for assessment; these materials explain their origin.

| Material | Purpose |
| --- | --- |
| [sources.json](sources.json) | Original URLs, versions, coverage, downloaded-file hashes and local cache locations |
| [crosswalk-v1.json](crosswalk-v1.json) | 46 conceptual mappings covering all dimensions in the 16 collected rubric summaries |
| [source-rubrics/](source-rubrics/) | Provider-specific summaries, preserving native scales and the archived grade-6 contract |
| [standards/](standards/) | Selected text-observable CCSS Writing/Language profiles |
| [project-writing-v1.json](project-writing-v1.json) | Reconstruction template from which the finalized grade files were produced |

## Collected sources

Collected September 8, 2026: 16 rubric documents plus one CCSS standards document.
“All sources” means this collection, not every rubric used in the United States.

| Source | Coverage | Native scoring |
| --- | --- | --- |
| UEN, 9 rubrics | K–2, three genres per grade | Focus/organization 1–4; conventions 0–2 |
| Smarter Balanced, 5 rubrics | Opinion/informational 3–5; argumentative/explanatory 6–11; narrative 3–8 | Two writing dimensions 1–4; conventions 0–2 |
| Oregon, 2 guides | High-school narrative and informative/argumentative | Six traits 1–6; informative/argumentative adds source use 1–6 |
| CCSS ELA | K–12 Writing/Language expectations | Standards, not a scoring scale; 9–10 and 11–12 are grade bands |

UEN publication versions are unconfirmed. Smarter Balanced rubrics were updated in August
2022; Oregon guides were adopted in 2019. Oregon is a high-school guide, not a separate
grade-12 norm. CCSS Writing appears on printed pages 19–21 and 42–47; Language on 26–29 and 52–55.

## Reconstruction decisions

Content/purpose and organization were separated. Observable voice, word choice and sentence
fluency were grouped under expression; inferred personality and motivation were excluded.
Conventions received new 1–4 descriptors. Source attribution/fidelity is conditional and
separate from reasoning. UEN does not independently score every project domain; early-grade
language expression is a project addition guided by selected Language standards.

The crosswalk explains each split/merge. It establishes no numeric equivalence, preserves no
implicit provider weighting, and does not convert existing provider scores. Grade standards
and genre requirements constrain the new ratings. Scores are grade-relative, not calibrated
across grades. Student-authored text is supported; drawings, dictation and research process
cannot be inferred from the final essay.

The common project rubric uses null scores for insufficient assessable text or non-English
responses; off-topic writing can still be scored by domain. This differs from source NS rules.
Provider adapters retain their original contracts: UEN/Smarter Balanced NS categories;
Smarter Balanced off-purpose responses withhold all app scores even though source conventions
may be scored; Oregon `insufficient_evidence` is a project abstention, not an official NS score.

## Reproduction and compatibility

Inference reads finalized grade files. The template is retained for the reconstruction record;
`python -m writing_synthesis.cli.materialize_project_rubrics --check` checks their correspondence without
writing. Run this command from `writing_data_synthesis`. The command without `--check`
rebuilds the grade JSON files and should only be used when intentionally revising them.

Old provider requests, source catalogs and saved records still use the preserved summaries
and metadata here. Existing default routes are unchanged; explicit `project-writing-v1`
selects the finalized grade files. Source/criteria hashes, selected standards, exact prompts
and the grade-file hash are retained with runs. Mock checks verify contracts and persistence,
not writing quality or human-rater agreement.

## Originals and attribution

The 17 original PDF/DOCX files and text extracts remain in the ignored repository directory
`.local-data/writing-data-synthesis/reference-materials/2026-09-08/`. `sources.json` records
how to locate and verify them. Source scoring examples are linked, not collected student data.

CCSS: © Copyright 2010. National Governors Association Center for Best Practices and
Council of Chief State School Officers. All rights reserved.
See the [CCSS public license](https://www.thecorestandards.org/public-license/).
The repository’s MIT license does not replace third-party source terms.
