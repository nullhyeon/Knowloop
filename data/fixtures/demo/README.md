# Demo Fixture Pack

This directory stores the deployment-grade sample data pack for judge-facing demos.

Goals:
- keep the canonical test fixture pack unchanged
- seed runtime data with richer student/instructor stories
- preserve English retrieval keywords where the current backend depends on them
- present Korean-friendly labels, summaries, and flow descriptions in the UI

The demo seed command reads this pack and populates mutable runtime storage under `data/`.
