# Optional language packs

The portable runtime and a new source installation omit three language-specific
components. OCR models, translation models and audio voices continue to use their
existing separate downloads.

| Pack | Used for | Download (decimal MB, Windows Python 3.10) |
| --- | --- | ---: |
| Japanese word lookup | Janome word boundaries for Japanese source text | 19.7 |
| Chinese word lookup | jieba word boundaries for Chinese source text | 19.2 |
| Japanese pronunciation | OpenJTalk, SudachiPy and Sudachi dictionary; speech and phonetic notation | 103.5 |

Select Japanese or Chinese as **Text language**, then use **Download required
files** to prepare its word lookup pack along with OCR/translation. Merely choosing
a language does not download anything. Other source languages do not need these
word lookup packs, even when translating *into* Japanese or Chinese.

Downloading a Japanese voice also prepares the pronunciation pack. For phonetic
notation without audio, leave audio disabled, enable **Show IPA in word popups**,
and use **Download pronunciation**. The roughly 103.5 MB pack does not include the
audio model. The speech button shows the combined size of missing components when
audio is enabled.

**Manage local files** offers individual pack checks/downloads and removal. Packs
are shared across language pairs in `%LOCALAPPDATA%\LanguageLens\language-packs`.
Removing one affects its capability only; translation models and voices are kept.
If a Windows process still has a dictionary or DLL open, removal disables the pack
immediately but some disk space may remain occupied. Restart Lens and remove the
pack again to reclaim those files. Maintenance is blocked during capture and other
file operations in the app.

## Integrity and updates

The app ships a catalog of exact versions, official upstream URLs, byte counts
and SHA-256 checksums. It never resolves a floating "latest" version. Pack downloads
contain Python code and, for Japanese pronunciation, native binaries, so compatibility
with the executable matters. Downloads are verified before bounded extraction;
archive paths and links are checked, and installation scripts are never run.
Upstream package notices accompany the extracted files. Models retain their own
licences; the repository licence does not supersede dependencies' terms.

Each installation has a version fingerprint and an atomic active pointer. Failed
or cancelled replacements retain the previous published installation. The old
app can continue using its compatible pack. A **new** app whose catalog changes
may require a new pack before that capability becomes ready; unrelated languages
remain available. Successful replacement retires the previous managed pack. This
is not a multi-version rollback manager or an automatic update service.

Cheap file checks drive UI readiness. Workers verify installed file hashes before
first use, and capture/synthesis never downloads missing components. Full checks
redownload a damaged pack; individual wheels within a failed pack transaction are
not cached. A process forcibly stopped mid-download may leave a staging folder;
the next successful install or removal cleans unused folders for that pack.

To update a pack deliberately:

1. Update `PINS` in `scripts/update-pack-catalog.py` and the `language-packs` extra
   in `pyproject.toml`. Update matching constraints when changing the release snapshot.
2. Run the catalog script. Review the versioned upstream artifacts and licences;
   the script fetches official PyPI metadata and never changes versions on its own.
3. Test dependencies against the base runtime, including native ABI requirements.
   Update explicit core dependencies and packaging hidden imports when needed.
4. Build and test both empty and installed pack storage, offline Japanese/Chinese
   segmentation, Japanese phonetic notation/synthesis, failed updates and removal.
5. Ship the reviewed catalog with an app release. Security updates use this same
   deliberate process; pins do not automatically deliver upstream fixes.

The pronunciation catalog has Windows x64 wheels for Python 3.10–3.12, with each
interpreter selecting its matching ABI. The portable build uses Python 3.10.
Pure Python word lookup packs are independent of that native ABI. Source developers
can alternatively install `.[dev,language-packs]` with the release constraints;
matching preinstalled libraries are accepted in source mode. Managed pack removal
does not uninstall those developer dependencies. The portable app always uses its
managed packs, regardless of Python installations elsewhere on the machine.

## Packaged verification

Create fixtures through the actual packaged worker (explicit network access):

```powershell
.\.venv\Scripts\python.exe scripts/prepare-release-pack-fixtures.py `
  --bundle artifacts/releases/<run-id>/dist/LanguageLens `
  --output artifacts/pack-validation
```

Then run `scripts/verify-release.py` with `--language-packs
artifacts/pack-validation/LanguageLens/language-packs`, plus the existing `--fixtures`
and `--voices` options for full offline inference. Omit `--language-packs` for the
base-only check. The verifier copies pack files with their timestamps into isolated
storage and strips Python/repository search paths.
