# Pinned Steam cloud build

The production build defaults to the Steam Dedicated Server source. It downloads only `ShooterGame/Content/Paks/pakchunk0-WindowsServer.pak` from app `2430930`, depot `2430931`, manifest `3251368963427721326`, using the anonymous mode of DepotDownloader 3.4.0. The server PAK and Steam metadata are temporary files under ignored `work/server-depot/`.

Before editing translations, the build extracts and parses exactly four source LOCRES files. Each must match the pinned size, SHA-256, LOCRES version 3, and entry count:

| Resource | Size | SHA-256 | Entries |
| --- | ---: | --- | ---: |
| ShooterGame EN | 3,669,617 | `efb6606905da0c3b5883c2472b253db5e22f5cd2e948cb0d1601b565ce41a216` | 39,444 |
| ShooterGame RU | 4,996,378 | `be8b5d46901bc3780be0454dbc9545908cdb35b6cc59cd5dd48315d9887a1d44` | 35,598 |
| Engine EN | 3,909,182 | `c0ae7e3dc9fb0f38ab39064f4556737c7ebf3a7ed8bd3971dd6dd0912ddf2d30` | 48,284 |
| Engine RU | 5,805,962 | `4e9e6bc08b577c947ec67bc1168633916f464d45ce973c8a5f6de54159a9d475` | 45,771 |

The build keeps the v1 translation semantics: 1200 ShooterGame corrections, 43 explicit additions, and 21 Engine edits (20 corrections plus one addition). Placeholder, printf and RichText validation runs before serialization. repak then writes a V11 patch containing only the two patched Russian LOCRES files; `info`, `list`, `unpack`, byte comparison and reparse must pass. The final artifact is accepted only at 10,795,036 bytes and SHA-256 `914589668aa41516915a68ef233873f4aeeedf570db70a7232e36ff9e8c04f2b`.

## Running

```powershell
python tools/bootstrap.py
python build.py --source steam --manifest 3251368963427721326
python tools/cloud_report.py
```

For an already-downloaded pinned server PAK, local deterministic verification can skip Steam access:

```powershell
python build.py --source server-pak --server-pak PATH_TO_SERVER_PAK --output work/cloud-validation/ASA_RU_Fix_P.pak
```

`--source installed-game` remains available as a developer fallback. The manual GitHub Actions workflow is [`../.github/workflows/cloud-build.yml`](../.github/workflows/cloud-build.yml). It has only the `workflow_dispatch` trigger and uploads the PAK, a JSON report and compact validation log with three-day retention. It does not publish releases, tags or commits.
