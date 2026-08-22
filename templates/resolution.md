---
# Template: Board Resolution

layout: default
title: "Resolution YYYY-NNN"
date: YYYY-MM-DD
nav_order: YYYYNNN
parent: Resolutions

type: resolution
number: "YYYY-NNN"
status: adopted       # proposed | adopted | rescinded
adopted_date: YYYY-MM-DD
vote_for: 0
vote_against: 0
vote_abstain: 0
---

# Resolution {{ page.number }}

**Adopted:** {{ page.adopted_date | date: "%B %d, %Y" }}

---

## WHEREAS

[Recitals explaining the background and rationale]

## NOW, THEREFORE, BE IT RESOLVED

[The actual resolution language]

---

## Vote

| For | Against | Abstain |
|-----|---------|---------|
| {{ page.vote_for }} | {{ page.vote_against }} | {{ page.vote_abstain }} |

---

*Certified by the Secretary of the Board*
