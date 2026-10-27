# Repository hooks

Enable the tracked hooks once per clone:

```sh
git config core.hooksPath .githooks
```

The executable `pre-commit` hook runs:

```sh
catalog +d credentials +d credentials_deployment +d credentials_test +d credentials_development +d training +d test_screenshots create
```

It then stages only `catalog.cat` for the same commit. A missing command, generator
failure or staging failure stops the commit. By default `catalog` must be on the
Git client's PATH. An executable override supports PyCharm or other Git clients
without an activated virtual environment:

```sh
git config --local catalog.command /absolute/path/to/catalog
```

The catalogue describes the working files, including any unstaged edits. The hook
does not stage those edits. Hook configuration persists across branch changes;
each branch needs the tracked `.githooks/pre-commit` file.
