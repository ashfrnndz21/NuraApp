# Closing an account — awaiting counsel's sign-off

**Status** drafted for counsel, not yet signed off · **Issue** #143 · **Code** `app/identity/closing.py`, `app/consent/closing_words.py`

A person can withdraw "keep my papers" (`hold_health_record`) only by closing his account. The PDPA asks that a withdrawal be possible on reasonable notice, with its consequences explained. This page is what he is shown, what then happens, and the retention window. **Counsel is asked to sign off the wording and the window before any real data** (see *Questions for counsel*).

## What he is shown

The confirm step shows these lines, and his yes binds to exactly them: the words and the day. A yes to other words is refused (`NotWhatWasConfirmed`).

| | English | Malay | Chinese |
|---|---|---|---|
| 1 | Nura will stop keeping your papers. | Nura akan berhenti menyimpan surat-surat anda. | Nura 会停止保存您的文件。 |
| 2 | Nobody can open them from now on, not even you. | Tiada sesiapa boleh bukanya mulai sekarang, termasuk anda. | 从现在起，谁都不能打开，包括您自己。 |
| 3 | Nura will not remind you about your medicines. | Nura tidak akan ingatkan anda tentang ubat anda. | Nura 不会再提醒您用药。 |
| 4 | Your family will not be told when you are unwell. | Keluarga anda tidak akan diberitahu apabila anda tidak sihat. | 您不舒服时，不会再通知您的家人。 |
| 5 | If you are unwell, call {emergency_number}. | Jika anda tidak sihat, telefon {emergency_number}. | 如果您不舒服，请拨打 {emergency_number}。 |
| 6 | Your papers will be deleted after {day}. | Surat-surat anda akan dipadam selepas {day}. | 您的文件会在{day}之后删除。 |
| 7 | Until then, you can change your mind. | Sebelum itu, anda boleh ubah fikiran. | 在那之前，您可以改变主意。 |

`{day}` is the last day of the window, said his way ("Wednesday 15 October"); the window runs to the end of that day on his wall clock, so "until then" means the whole of it. `{emergency_number}` is the region's (995 in Singapore, 999 in Malaysia).

## What happens, at once

- **His own record stays his to read.** Every agreement he gave and his trail (who reached his papers, and when) stay open to him, and to nobody else, for the whole window. That is his PDPA access right. Nothing else does, not even his own papers.
- **Nobody opens his profile.** Every key (his family's, a helper's, an emergency contact's) and his own reads are refused by name (`AccountClosing`), and each refused reach is on his trail. Only the closing's status and his undo stay open to him.
- **Keeping his papers is withdrawn**, on the record: the `hold_health_record` consent is marked withdrawn, by him, at that moment.
- **The family's WhatsApp group is emptied**, and nothing is mirrored into it. A red word still posted there is answered to its sender alone, with the number to call.
- **Nothing more is sent about him.** Every push subscription under the profile is revoked, and the delivery engine sends nothing about him.
- **One exception, for safety.** A red flag raised *before* he closed the account is still carried to his family, rung by rung, until someone answers. It is never hidden from the day it was raised. Someone it reached can still say they have it, in the app or by answering on WhatsApp, and then nobody else is asked.

## Undo

Until the window ends, his yes undoes it. He agrees again to today's words for keeping his papers (a new `hold_health_record` consent), and the suspension lifts: his keys and his family's work again at once, and everyone who said yes to the family's WhatsApp group is back in it. Phones must subscribe to reminders again.

## After the window: erasure (PDPA data map §4)

The erasure job (`run_erasures`, behind the `Eraser` port) runs from the region's scheduler. On a dev run, `POST /dev/run-erasures` runs it.

- **Kept, outside the graph (`erasure_record`):**
  - every consent row as it stood (what he agreed to, and when he withdrew);
  - who asked;
  - when he asked;
  - when the graph was erased;
  - counts of what went (no content).
- **Kept:** his sign-in account (the `person` row). Deleting the account itself is a separate request.
- **Deleted:**
  - every row of profile data, including the audit trail, deliveries, ladders, push subscriptions and the profile row;
  - every stored object under `<kind>/<profile_id>/` for each kind Nura keeps (photos, PDFs, recordings, notes, documents, messages, and a card's spoken twin).

## The window

`NURA_ACCOUNT_RETENTION_DAYS`, **30 days until counsel says otherwise.**

## Questions for counsel

1. Do the five lines explain the consequences well enough for a withdrawal under the PDPA (Singapore) and PDPA 2010 (Malaysia)?
2. Is 30 days a reasonable window before deletion, and must it differ between Singapore and Malaysia?
3. The archived consent rows and the erasure record are kept after the graph is erased. For how long, and on what basis?
4. Must the person be sent his consent record and audit trail before erasure (the data map's step 1)? Today the DPO sends them on request.
6. The archived consent rows keep the wording he agreed to, and the names of the people he let in and of any witness. For how long may they be kept, and must a family member be told when their name is kept after his papers are erased?
7. If the region's bucket keeps object versions, a delete leaves the older versions behind until the bucket's own lifecycle rule removes them (`docs/deploy.md`). Is a lifecycle rule of 30 days on old versions enough?
5. During the window his family is not told when he is unwell, except for a red flag raised before he closed. Is that the right line?
