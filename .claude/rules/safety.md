---
paths:
  - "backend/app/reasoning/**"
  - "backend/app/safety/**"
  - "backend/app/search/**"
---
# Clinical safety rules

- Outputs are patterns to discuss with a clinician, never diagnoses. The boundary line accompanies any inferring output.
- Red flags (chest tightness, breathlessness at rest, one-sided swelling, worst-ever headache, sudden blurring, a fall, confusion, shaky-and-sweaty on sugar medicines, 1 kg or more in two days after a heart discharge) bypass planning and ranking: escalate immediately.
- Flags that depend on a missing fact are suppressed, with the suppression visible to the caregiver.
- Interaction, identification and dosing facts come only from the licensed drug data client; never from model output.
- High-risk drugs (warfarin, insulin, digoxin, methotrexate, opioids) cannot be saved from voice or text alone; a label photo is required.
- Search sources are allowlisted; uncited compressed output is rejected; anything that would change treatment is rerouted as a doctor question.
