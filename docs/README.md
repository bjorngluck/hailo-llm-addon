# Hailo LLM — Technical Documentation

This folder contains detailed technical and architectural documentation for the Hailo LLM Home Assistant addon.

## Contents

- [Architecture Overview](architecture.md) — System design, components, data flow, and diagrams
- [Dependencies](dependencies.md) — All runtime, build, and hardware dependencies with versions and rationale
- Diagrams (embedded in the architecture document using Mermaid for GitHub rendering)

## Intended Audience

- Developers and contributors who want to understand or extend the addon
- Power users troubleshooting persistence, API compatibility, or hardware integration
- Anyone evaluating the project for production use on HAOS + Hailo hardware

## Quick Links (User Facing)

For end-user documentation see the [root README.md](../README.md) in this repository.

## Versioning Note

Documentation in this folder targets the current major version (v2.0+). Older behavior is noted where relevant in the changelog.

## Contributing to Docs

When you make architectural or dependency changes, please update the files in this folder (and the main README if user-facing impact exists). Mermaid diagrams are preferred for diagrams because they render natively on GitHub and stay in source control.
