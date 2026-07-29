# Sandcastle microVM operations

Sandcastle runs every phase—planning, implementation, review, and merging—in a Docker Sandboxes microVM. Every open issue labeled `sandcastle` is processed in this runtime.

The default local template is `parames-sbx:dev`, built from `Dockerfile.sbx`. The defaults allocate 4 CPUs, 8 GiB, and a ten-minute lifecycle timeout; override them with the `SANDCASTLE_SBX_*` variables in `.env.example`. Set deployment and invocation IDs in CI so castle names are ownership-scoped.

Before scheduling work, run on a supported nested-virtualization host:

```sh
sbx version
sbx diagnose
sbx template ls
```

Each phase gets an isolated castle; implementation and review for one issue share a single castle. No ports are published by default. Inspect only named project castles with `sbx ls`; remove a known stale owned castle with `sbx rm --force <exact-name>`. Never bulk-delete unrecognised names.

Build templates from `Dockerfile.sbx` in a trusted pipeline. Templates and diagnostics must not contain repository source or secrets.
