"""Outbound WhatsApp: what the number sends, and the rules every send obeys (E19-01, E19-03).

Nothing goes out without the profile's WHATSAPP consent in force. Outside the 24-hour
customer-service window the only thing that may go out is one of the six approved templates
with its slots filled; inside it, free text from the reply catalogue as well. Every send is
a SHARE line on the trail, channel WHATSAPP, naming who it went to, and every template send
names the State it was composed from. `send` is the one door; `level0` is the patient's
day through it — the morning card, the feeling check-in, the visit card, the family notice —
each a function a scheduler (E11) will call, none scheduled yet.

This directory is CODEOWNERS-protected: a change here is reviewed by a person.
"""
