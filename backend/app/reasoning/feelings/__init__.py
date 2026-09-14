"""The feeling cloud and feeling inference (E17-01, E17-02).

`words` is the fixed tables: the base words, what brings a word forward, the one question a
tap asks back. `record` reads what the cloud and a tap are read against. `cloud` weighs the
words from State with a reason for each; `inference` reads a tap and its answer against the
medicines, his blood pressure and this week's visits into a note of at most two things to tell
the doctor, with the boundary last; `service` is the door: a tap, an answer, the notes. A red
word never reaches any of it: it goes to the red-flag path first (`app.safety.red_flags`).
"""
