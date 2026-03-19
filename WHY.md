# WHY.md — draft for ~/dev/mk/lrc-match/WHY.md

---

# Why lrc-match exists

## The problem with music recommendations

Every major streaming platform recommends music the same way: **collaborative filtering**.

"People who listened to X also listened to Y."

It's a behavioural graph, not a semantic one. It clusters music by audience demographics — not by what the music actually means.

The result: John Lennon gets recommended alongside other 1970s classic rock, because that's who 50-year-olds listen to together. Not because "Imagine" shares emotional DNA with anything made this decade. A 2023 indie track about disillusionment and longing for peace could be closer to "Imagine" than most of Lennon's contemporaries — but collaborative filtering will never surface it.

**lrc-match takes a different approach: semantic similarity based on meaning, not listening behaviour.**

---

## The difference

| | Spotify / Apple Music | lrc-match |
|---|---|---|
| Method | Collaborative filtering | Vector embeddings |
| Question | Who else listened to this? | What else *feels* like this? |
| Era-aware? | Yes (clusters by generation) | No — era-blind |
| Genre-aware? | Yes (clusters by genre) | No — genre-blind |
| Based on | Listening behaviour | Lyric meaning |

---

## What this looks like in practice

### Era-blind matching

Fed a chunk of Britney Spears' *Crazy* (1999):

> *My heart is jumping, it's easy to see*
> *You drive me crazy, I just can't sleep*
> *I'm so excited, I'm in too deep*
> *Whoa-oh, crazy, but it feels alright*

Top match: **"Excitable" — Def Leppard (1987)**

12 years apart. Opposite ends of the genre spectrum. Same emotional DNA: heart racing, can't sleep, overwhelmed by infatuation. The model didn't care about production style, decade, or cultural prestige. It found the twin.

Music snobs will hate this. That's the point.

### Meaning without keywords

Query: *"boyfriend gaslights and women recovered"*

Results:
- **"Under Control" — Ellie Goulding**
  *"Your love was never the missing key / I feel like I'm breathing again"*
  The model understood: misplaced dependency on someone who wasn't helping, the illusion collapsing, recovery. The word "gaslighting" appears nowhere in the lyrics.

- **"Dance in the Dark" — Lady Gaga** (Section 2, score: 0.6057)
  *"Her boyfriend says she's a mess / She's a mess, she's a mess"*
  The model understood that "she's a mess" is the boyfriend's words being internalised and echoed — not self-description. Power dynamics in language, captured without any explicit label.

### The full results picture

Same Britney *Crazy* chunk, full results ranked by similarity score:

| Score | Song | Artist |
|---|---|---|
| 0.6529 | Hitchhiker | Demi Lovato |
| ~0.65 | Waiting on You | Céline Dion |
| 0.6108 | Crazy For You | Adele |
| 0.5959 | Speechless | Beyoncé |
| ~0.59 | So Emotional | Christina Aguilera |
| ~0.59 | Neon Lights | Demi Lovato |
| ~0.58 | Excitable | Def Leppard |

1987 hair metal. 1990s Céline Dion. 2000s Britney. 2010s Adele and Beyoncé. All in the same neighbourhood. The model is also ranking *degree* of similarity — not just yes/no matches but a gradient of emotional closeness.

### Meaning you didn't know was there

"Dance in the Dark" was heard for years as a literal late-night dancing song — the production is loud, the hook is catchy, the meaning buried.

A semantic search surfaced the specific section with the gaslighting dynamic. The meaning was always there. lrc-match found it.

**This is the real value: not finding more songs to listen to. Understanding what you're already listening to.**

---

## What lrc-match is not

- Not a Spotify replacement
- Not a recommendation engine based on your listening history
- Not trying to predict what you'll like

It's a semantic search engine for your own music library. You bring the library. You ask the questions. It finds meaning.

---

## The Jellyfin connection

If you're self-hosting Jellyfin, you already believe your music library belongs to you. lrc-match extends that: your music's *meaning* belongs to you too. No data sent to streaming platforms. No algorithm deciding what you should feel next. Just your library, searchable by what matters.
