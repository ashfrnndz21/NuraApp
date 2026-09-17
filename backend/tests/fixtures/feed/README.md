# Feed fixtures (E21)

What the fixture searcher and compressor answer with, until the real fetcher and the
grounded model call exist behind the same two ports (`app/delivery/feed/compress.py`).

- `searches.json` — `{"<job kind>:<term>": [page, …]}`. Each page names its `domain`, `url`,
  `title`, `published_at` and `text`. The searcher returns only pages whose domain is among
  the allowlisted domains it was asked for, so the `supplement-shop.example` page here is
  never returned: it is the test that the allowlist holds.
- `compressions/<sha256 of the page text>.json` — `{"<language>": {headline, body, why_topic,
  passage}}`: the lines a card says, in each language the fixture speaks, and the passage of
  the source they came from. No `passage` means uncited, and the finding is rejected. The
  warfarin INR page compresses to lines that would change a dose: the engine reroutes it as
  a question for the doctor (`QUESTION`, held for the memo), never a card.

- The `safety:warfarin` page is a recall notice naming a batch. The engine matches it against
  the `medicine.batch` fact read off his pack photo: no match, and the notice is held for the
  caregiver and never sent to him.

Nothing here is pharmacology the model wrote: the texts are paraphrases of public consumer
pages from the seeded sources, and the compressed lines are what a pharmacist would let
stand. Add a page by adding both files.

- The `explainer:diabetes` page is HealthHub's consumer page on diabetes, for a profile that told
  the condition when it was set up (E01): the learning supply is made per condition as well as
  per medicine (E21-06). Its compression speaks English, Malay and Chinese.
- `worth_knowing:diabetes` reuses that same HealthHub page's text (its own compression fixture
  is found by the text's sha256, so nothing new is added there) under the broker's own job
  kind, for the `did_you_know` rule's own topic pick when it lands on a condition rather than
  a medicine (`app.delivery.recommend.rules.did_you_know`).
