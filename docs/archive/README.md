# Archive

Historical documents from the development of nanorunner. These files are
preserved for reference but are not actively maintained. The current state
of the codebase is the source of truth; if an archive document and the code
disagree, trust the code.

## Layout

```
archive/
|-- README.md            (this file)
|-- audits/              Dated audit reports
`-- plans/               Design plans and implementation specs
```

## Audits (`audits/`)

- `2026-04-29-orphans-simplification.md` -- code/docs audit identifying
  transitional CLI shims, duplicated genome resolution logic, and dead
  worker-pool scaffolding.

## Plans (`plans/`)

Design specifications and implementation plans, paired by date:

- `2026-02-05-expanded-mocks-design.md` /
  `2026-02-05-expanded-mocks-implementation.md` -- additional mock
  community presets.
- `2026-02-05-species-mocks-design.md` /
  `2026-02-05-species-mocks-implementation.md` -- species name resolution
  and mock community generation.
- `2026-02-25-simplification-design.md` /
  `2026-02-25-simplification-implementation.md` -- module simplification
  pass.
