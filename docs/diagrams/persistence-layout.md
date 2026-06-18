# Persistence Layout

## Directory Tree (inside the running addon)

```
/data/                        # HAOS persistent volume (survives everything)
├── models/                   # Primary model storage (HEF files + metadata)
│   └── <model-name>/
│       └── ...
├── chats/                    # Server-persisted conversations
│   ├── 550e8400-e29b-41d4-a716-446655440000.json
│   └── ...
└── options.json              # Addon configuration (read-only from our side)
```

## How It Is Populated

- `run.sh` creates the directories and sets `OLLAMA_MODELS=/data/models`
- Defensive symlinks are created so the binary finds models regardless of internal path assumptions
- Chat files are written by the Flask application when conversations are created or updated
- Nothing is written to the container's ephemeral layers for user data

## Benefits

- Standard HA addon contract — users get automatic backup behavior when they back up HA
- Survives addon reinstall (as long as the addon slug stays the same)
- Easy to inspect with `docker exec` into the addon for debugging

## What Is *Not* Persisted

- The running model in RAM (controlled by `keep_alive`)
- Any temporary conversion artifacts during pull (they end up in the persistent models dir once complete)
```

## Next Steps

I now have:

- Full public README.md (root)
- docs/README.md
- docs/architecture.md (with multiple Mermaid diagrams inline)
- docs/dependencies.md
- docs/diagrams/component-diagram.md
- docs/diagrams/persistence-layout.md

This satisfies the request well.

To make it nicer, I could add a simple Mermaid in the persistence one or leave it.

Optionally, update the old DOCS.md to link to /docs, but it's already quite good.

Now, commit the documentation work.

Since the user said "I will review", pushing or just having the files on the branch is fine — but to be complete, stage and commit.

The branch is already pushed earlier, so new commit will be ready for user to pull or they can see it.

Let's commit.