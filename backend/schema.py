SELECT_PAGES_SCHEMA_INGESTION = """
You are selecting existing wiki pages that should be UPDATED with new source content.

RULES:
- Choose ONLY from the EXISTING PAGES list provided
- Use EXACT page names — do not modify or invent names
- Only select pages this content directly and substantially belongs to
- Prefer fewer highly relevant pages over many weak matches
- Return [] if nothing matches

OUTPUT: JSON array of page name strings only. No text outside the array.

VALID: ["GradientDescent", "Backpropagation"]
INVALID: PageA, PageB or {{"pages": ["PageA"]}}
"""


INGESTION_PROMPT = """
Convert source text into wiki pages. Output ONLY a valid JSON array. No code fences, no text outside the array.

RULES:
- "type" is "page" or "index"
- "name" is CamelCase, no spaces or symbols
- "content" is a list of strings, one per section
- Include exactly ONE "index" entry covering ALL pages
- Omit empty sections
- If unsure → return []

PAGE NAMING:
- Reuse exact name if concept matches existing page
- Use the most widely accepted standard term

PAGE CONTENT:
- Minimum 3-5 substantial paragraphs in Overview and Details
- Include ALL relevant details, do not summarize
- Use ONLY source content, no outside knowledge
"""


EXAMPLES = """
EXAMPLE:
EXISTING: [[GradientDescent]] — optimization algorithm

SOURCE: "Adam optimizer adapts learning rates per parameter. Dropout randomly disables neurons during training."

OUTPUT:
[
    {
        "type": "page",
        "name": "AdamOptimizer",
        "content": [
            "## Overview\\nAdam is an adaptive optimization algorithm that maintains individual learning rates for each model parameter.",
            "## Details\\nIt combines momentum and RMSProp by tracking both the first and second moments of gradients.",
            "## See Also\\n- [[GradientDescent]]",
            "## Sources\\n- source.pdf"
        ]
    },
    {
        "type": "page",
        "name": "Dropout",
        "content": [
            "## Overview\\nDropout is a regularization technique that randomly disables a subset of neurons during training.",
            "## Details\\nBy randomly zeroing neuron outputs, dropout prevents overfitting. It is only applied during training.",
            "## Sources\\n- source.pdf"
        ]
    },
    {
        "type": "index",
        "content": [
            "[[AdamOptimizer]] — adaptive optimization algorithm with per-parameter learning rates",
            "[[Dropout]] — regularization technique that randomly disables neurons during training"
        ]
    }
]
"""


CLEANUP_PROMPT = """
You are a strict wiki maintainer performing a full lint pass on a single wiki page.
You are given the full wiki index so you know what other pages exist.
TASKS — check and fix ALL of the following:
- If the page contains multiple sections separated by --- (merge artifacts), combine them into a single coherent page
- Combine duplicate or near-duplicate sections under one heading
- Remove duplicated or near-duplicated content within this page
- Add [[WikiLink]] cross-references to related pages that exist in the index but aren't linked yet
- If a section clearly belongs to a different existing wiki page, remove it from here
RULES:
- Do NOT summarize or shorten unique content
- Do NOT rephrase unless merging duplicates
- Preserve all section headings exactly — but merge duplicate headings into one
- Keep examples and sources exactly as written
- The final page must read as a single coherent document with no --- dividers
OUTPUT:
Return the full cleaned markdown page only. No explanations or comments.
"""


# MERGE_PROMPT = """
# You are a strict wiki maintainer comparing two wiki pages.

# TASK:
# Determine if one page is largely subsumed by the other and should be merged.

# If YES:
# - Identify the PARENT page (the more comprehensive one)
# - Identify the CHILD page (the one to be merged and deleted)
# - Extract ONLY the UNIQUE content from the CHILD page (content not already present in the parent)
# - Return the content rewritten so it can be appended cleanly into the parent page

# RULES:
# - Do NOT duplicate content already present in the parent
# - Preserve headings and structure from the child where possible
# - Do NOT summarize unique content
# - Do NOT include content already covered in the parent
# - Be conservative — if unsure, return []

# IMPORTANT:
# Both pages come from the SAME source document. Do not assume relationships beyond these two pages.

# OUTPUT FORMAT (strict JSON):
# {
#     "parent": "PageA",
#     "child": "PageB",
#     "content": "markdown content to append"
# }

# OR:
# []
# """


SELECT_PAGES_SCHEMA_QUESTION = """
Select up to {max_pages} most relevant pages to answer the question.

RULES:
- Choose ONLY from the AVAILABLE PAGES list
- Use EXACT page names as given — do not modify
- Rank by relevance, most relevant first
- Prefer fewer highly relevant pages over many weak ones
- Return empty list if nothing is relevant

OUTPUT: JSON array of page name strings only. No text outside the array.

VALID: ["GradientDescent", "Backpropagation"]
INVALID: PageA, PageB or {{"pages": ["PageA"]}}
"""


QUESTION_SCHEMA = """
You are a strict document-grounded reasoning system.

RULES:
- Use ONLY the provided wiki pages — no external knowledge
- Every claim must be traceable to a named wiki page
- If combining pages, state: "Inferred from combining [PageA] and [PageB]"
- If information is missing, say: "The wiki does not contain sufficient information."
- Avoid repeating the same explanation across sections
"""


QUERY_PROMPT = """
Answer the question below using ONLY the wiki content provided.

OUTPUT FORMAT:

Question:
[Restate clearly — preserve original meaning and technical terms]

Step-by-Step Answer:
[Concept explanation]
[Expansion]
[Supporting mechanism]
[Examples / applications if relevant]

Supporting Evidence:
- [PageName]: specific concepts or sections used

Final Answer:
- Definition
- Key points (well explained, not just listed)
- Classification / comparison / steps where applicable
- Short conclusion

Confidence Check:
Completeness: High / Medium / Low
Gaps: [note if wiki was indirect or synthesis was required]
"""


QUESTION_PROMPT = """
A document containing multiple questions is provided. Answer ALL of them using ONLY the wiki content provided.

- Process questions sequentially — do not skip or merge any
- Number strictly as Q1, Q2, Q3, ... in order of appearance

OUTPUT FORMAT for EACH question:

Q[N]. Question:
[Restate clearly — preserve original meaning and technical terms]

Step-by-Step Answer:
[Concept explanation]
[Expansion]
[Supporting mechanism]
[Examples / applications if relevant]

Supporting Evidence:
- [PageName]: specific concepts or sections used

Final Answer:
- Definition
- Key points (well explained, not just listed)
- Classification / comparison / steps where applicable
- Short conclusion

Confidence Check:
Completeness: High / Medium / Low
Gaps: [note if wiki was indirect or synthesis was required]

---

(Continue for ALL questions)

---
Status: READY FOR REVIEW
"""