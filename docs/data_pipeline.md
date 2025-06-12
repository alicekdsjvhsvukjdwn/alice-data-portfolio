---
layout: default
title: Pipeline Data
---

# Pipeline « raw → tidy → Power BI »

```mermaid
flowchart TD
  A[Raw CSV / Excel] -->|tidy_pipeline.py| B(CSV normalisé)
  B --> C(Power Query)
  C --> D(Power BI Map + KPI)
