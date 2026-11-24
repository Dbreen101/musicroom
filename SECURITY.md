# Security

The Music Room holds people's accounts and the records artists sell. If you
find a way to get at something you shouldn't — someone else's account, data
or files, a record's audio, the server's own Mac — please tell us privately,
and don't use it.

**How to tell us:** on GitHub, open the repo's **Security** tab →
**Report a vulnerability** (a private report only the maintainer sees). Or
tell Daithí in person at the Green Room.

Please include what you did, what you could reach, and how to do it again.
We'll answer within a few days, fix it, and thank you in the release notes if
you'd like.

What already stands in the way, so you know what to test against:

- Every request to the rooms server needs an account's key; the server answers
  only about that account and what others made public.
- Account codes are long and random, and sign-in tries are limited.
- The master account's pages answer only on the server's own Mac.
- The app on your laptop answers only its own pages (not other web pages, not
  plug-ins, not public rooms' code).
- Plug-ins and public rooms' own code run in sealed frames with strict rules on
  what they may load.
- Uploaded pictures are opened only as ordinary pictures and only up to a
  sensible size; records and pictures have size limits.

Known limits, for this trial: the server speaks plain HTTP on a shared Wi-Fi,
so it is meant for the residency's own network only; the server is one Mac.
