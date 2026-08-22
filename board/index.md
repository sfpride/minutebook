---
layout: default
title: Board Meetings
nav_order: 2
has_children: true
---

# Board of Directors Meetings

Official minutes from regular and special meetings of the SF Pride Board of Directors.

## Meeting Schedule

The Board of Directors meets monthly, typically on the first Wednesday of each month at 7:00 PM.

## Archives by Year

{% assign years = site.board | group_by_exp: "item", "item.date | date: '%Y'" | sort: "name" | reverse %}
{% for year in years %}
- [{{ year.name }}]({{ year.name }}/) ({{ year.items.size }} meetings)
{% endfor %}
