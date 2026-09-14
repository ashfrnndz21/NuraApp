"""WhatsApp: the channel a family already talks on, with the assistant inside it (E19).

Nura cannot read anyone's WhatsApp. It has one business number per country, and it sees
exactly what is sent to that number: a private thread with each key holder, and forwards.
The sender's phone number is their identity, so scope enforcement is automatic — a message
from Mei's number is resolved to Mei's account and to the key she holds, and everything it
does happens inside that key context, through the same doors as the app.

Every inbound message is classified (`classifier`) into a document, a health event, a piece
of coordination, or everything else; only the first three are kept, and a health event is
kept as a *proposal* (`proposals`) that the poster confirms with a yes from the same number
before a fact is written. A red flag (`app.safety.red_flags`) is written down before
anything else and answered in the thread. Outbound (`outbound`) is a template outside the
24-hour window and free text inside it, always through the patient's WHATSAPP consent, and
every send is a SHARE line on the trail. The provider behind it all (`provider`) is a port;
the fixture adapter records sends and serves media from fixtures, and no Meta call is made
anywhere in this build.
"""
