# Ziokt ecosystem Releases

Download the ecosystem from [Releases](https://github.com/txmu/Ziokt-Releases/releases).
`catalog.json` in the `catalog` release links to immutable build releases and
records source repository, commit, actual CI run, artifact SHA-256 and file list.

Sources: Ziokt, Corium and Shadow6. All are owned by txmu. Publication does not
add browser-store signing, notarization, independent hardware verification or
mainnet governance approval. Failed workflows remain explicitly identified;
an uploaded binary is never labelled full business acceptance merely because
an artifact exists. Development installers retain their original signing state.

The collector examines trusted owner push/manual/scheduled/release events and
never publishes artifacts from fork pull requests. It performs no compilation.
Run `python tools/publish.py --source txmu/Shadow6 --run RUN_ID` to preserve all
available product artifacts from a specific completed build. The scheduled job
updates the catalog every 20 minutes. Older immutable build releases are kept.
