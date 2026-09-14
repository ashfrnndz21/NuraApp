# Plain words: the standard for everything the patient reads or hears

Every string on the patient's surface, on WhatsApp and in every voice note follows this. It is not a style preference; it is the reason he keeps using it.

---

## 1. The rules

1. **Plain is not clipped.** Whole, natural sentences with a subject: "A heart doctor talks about the water pill and bananas. It is 30 seconds long." Never fragments: "A heart doctor explains. Only the part for you. 30 seconds." A headline can be short; the line under it is a full sentence a daughter would say.
2. **One idea per line.** A second idea is a second line.
3. **Short words, short lines.** Under ten words where it can be done. No word he'd have to ask about.
4. **Call things what he calls them.** "Water pill", "the aspirin", "your blood pressure book", "the sugar tablet". The chemical name is small, second, and never alone.
5. **Say the day and the date.** "Monday 29 September", never "the 29th". "Thursday at 10", never "10:00".
6. **Say what to do, and when.** "Every morning, stand on the scale before breakfast", not "keep weighing".
7. **Say who does the next thing.** "Ash will book it." "Mei will pick you up at 9."
8. **Answer the question he'd actually ask.** "Is the water pill bad for my kidneys?" not "Is it making my kidney number go up?"
9. **Add the small reassurance that removes a worry.** "Water is OK." "It is not a worry." "This number only goes up."
10. **Numbers as digits, small and few.** "6 days out of 7." "1 kg." "148."
11. **Never a red word.** No "missed", "failed", "overdue", "non-compliant". "One tablet was late."
12. **Nothing to decode.** No abbreviations, no units he doesn't use, no "dose", "recheck", "follow-up", "flag", "log".
13. **The same words every time.** Once it's "your blood pressure book", it is never "the log", "the readings", or "the record".

---

## 2. Glossary

| Instead of | Say |
|---|---|
| Diuretic, furosemide | The water pill |
| Antihypertensive, amlodipine | Your blood pressure tablet |
| Statin, atorvastatin | The cholesterol tablet |
| Metformin | The sugar tablet |
| Dose | How much you take. "Half a tablet." |
| Adherence, confirmation | "Taken" |
| Reading, log | Your blood pressure. Your blood pressure book. |
| Result, panel, labs | Your blood test. Your kidney test. Your sugar test. |
| Creatinine, eGFR | Your kidney number. Your kidney filter. |
| Potassium | A body salt. Doctors call it potassium. |
| HbA1c | Your sugar test. Lower is better. |
| Orthostatic | Dizzy when you stand up |
| Oedema, fluid retention | Swollen legs. Water in the body. |
| Symptom | How you feel |
| Flag, alert, triage | "This one we do not wait for." |
| Red flag | "Dr Tan wrote this in your hospital letter." |
| Discharge summary | Your hospital letter |
| Follow-up, review | See Dr Tan again |
| Recheck | Blood test again |
| Guarantee letter, GL, coverage | Your insurance letter. "Your insurance letter is ready." |
| Panel hospital | "Gleneagles is on your insurance." |
| Referral | A letter to see the eye doctor |
| Fasting | No food after 12 midnight. Water is OK. |
| Explainer, clip | "In simple words." "A short explanation." |
| Feed, timeline, record | Your Today page. Your papers. |
| Logged, filed, saved | "I wrote it down." "Saved." |
| Escalated, notified | "Ash knows." "Ash and Mei know now." |
| Not medical advice | "This is not a doctor's advice. Ask Dr Tan." |
| Urgent / not urgent | "Today." / "Not a worry." |

---

## 3. The test every line passes

Before a string ships to the patient surface:

- Would his daughter say it to him this way, out loud, as a full sentence?
- Is there one idea?
- Is every noun something he already has a word for?
- Does it say the day, the date, and who does the next thing, if any of those apply?
- Read aloud in Hokkien, does it still make sense? (If a word has no everyday equivalent, the line is wrong, not the translation.)

Lines that fail go back. There is no "advanced" mode on the patient surface; the caregiver's app is where the fuller words live.

---

## 4. Voice

Every card is spoken, so every line is also a script. Short sentences with a pause between them. Numbers spoken as he'd say them: "one kilo", "six days out of seven". The doctor's name every time, never "the clinic". No line longer than he can hold in his head while the next one plays.

---

## 5. Where this has been applied

All patient-facing text in the prototypes: Today, medicines, records, visits, the questions card, the not-feeling-well flow, the food photo, the three clips, the emergency card, the feeling cloud and its replies, the appointment planner's card, the Doctor Memo's patient cards and memo. The caregiver's screens keep their fuller wording, with sources.

---

## 6. The same words in Malay and Chinese

His words for things, in the three languages Nura speaks, so a line says the same thing on the card, in the voice note and on WhatsApp. The Malay and Chinese here are the words the catalogues already use, chosen where they disagreed; they are a first translation awaiting a native speaker's pass, like the lines themselves. A line whose English says the phrase in the first column says the Malay and the Chinese beside it (a longer phrase that holds them passes: "ubat tekanan darah anda"). The last column is the words never said for the same thing. `make language` checks every catalogue against this table (`backend/app/language/`).

| English | Malay | Chinese | Never |
|---|---|---|---|
| water pill | pil air | 去水药 | |
| blood pressure tablet | ubat tekanan darah | 血压药 | |
| cholesterol tablet | ubat kolesterol | 降胆固醇药 | |
| sugar tablet | ubat gula | 降糖药 | |
| blood pressure book | buku tekanan darah | 血压本 | |
| blood test | ujian darah | 验血 | zh "血检" |
| kidney test | ujian buah pinggang | 肾检查 | zh "肾脏检查" |
| sugar test | ujian gula | 血糖检查 | zh "糖化血检" |
| kidney number | nombor buah pinggang | 肾指数 | |
| body salt | garam badan | 身体的盐 | |
| swollen legs | kaki bengkak | 腿肿 | |
| how you feel | apa yang anda rasa | 感觉 | |
| This one we do not wait for | yang ini kita tidak tunggu | 这个我们不等 | zh "这个不能等"; zh "这个我们不能等" |
| hospital letter | surat hospital | 出院信 | zh "医院信" |
| insurance letter | surat insurans | 保险信 | |
| your papers | surat-surat anda | 文件 | en "your record"; en "'s record"; ms "rekod" |
| Today page | halaman Hari Ini | “今天”页面 | zh "今日页面" |
| In simple words | kata-kata mudah | 简单的话 | |
| not a doctor's advice | bukan nasihat doktor | 不是医生的意见 | zh "医生的建议" |
| medicine label | label ubat | 药盒标签 | zh "药的标签" |
| shaky and sweaty | menggigil dan berpeluh | 发抖又出汗 | zh "发抖出汗" |
| emergency card | kad kecemasan | 紧急卡 | |
| private notes | nota peribadi | 私人笔记 | |
| the pharmacist | ahli farmasi | 药剂师 | |
| I wrote it down | Saya sudah tulis | 我记下了 | ms "sudah tuliskannya"; zh "我已经记下了" |
| Water is OK | Air kosong boleh | 喝水没问题 | ms "Air tidak mengapa" |
| knows now | sudah tahu | 已经知道了 | |
