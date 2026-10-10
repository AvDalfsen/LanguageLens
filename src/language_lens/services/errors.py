"""Privacy-safe failure categories: never display arbitrary exception text."""
from dataclasses import asdict, dataclass
import errno
from urllib.error import HTTPError, URLError
from language_lens.runtime import recovery_instruction


class KnownTaskError(RuntimeError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class Failure:
    code: str
    stage: str
    message: str

    def event(self) -> dict:
        return {"error": self.message, "failure": asdict(self)}


MESSAGES = {
    "sentence_language": "A translation route needs an unsupported sentence language. Choose another route or update Language Lens.",
    "sentence_split": "The sentence splitter could not preserve this selection. Try a shorter passage and check required files in Settings.",
    "missing_pack": "A language pack is missing or changed. Open Settings and download the required language pack under 'Manage local files'.",
    "pack_restart": "A language pack changed while it was in use. Restart Language Lens to use the updated pack.",
    "pack_platform": "This language pack needs Windows x64 and a supported Python runtime. Use the Windows portable release.",
    "disk_full": "There is not enough disk space for the local files. Free some space, then retry.",
    "permission": "Windows denied access to the local files. Check folder permissions and whether another program is locking them, then retry.",
    "network": "The download server could not be reached or the connection failed. Check your connection and retry the download. Existing installed files are retained.",
    "timeout": "The operation timed out. Retry; for OCR or pronunciation, try selecting a shorter passage.",
    "route_unavailable": "No downloadable translation route is available for this language pair. Choose another 'Text language'/'Translate into' combination and try again later.",
    "missing_assets": "Required local files are missing or changed. Use 'Download required files' or 'Check required files' in 'Settings', then retry.",
    "integrity": "The downloaded files failed verification. Retry the download; existing installed models are retained.",
    "runtime": "A required local component could not be loaded. " + recovery_instruction(),
    "inspection": "The local models could not be checked. Click 'Retry file check'. Their installation status is unknown; no files have been removed.",
    "execution": "The local task could not complete. Retry the task; if it fails again, use 'Check required files' in 'Settings' and open the diagnostics folder.",
}


STAGES = {"status": "Checking local files", "prepare": "Preparing local files",
          "repair": "Replacing translation models", "remove": "Removing translation models",
          "ocr": "Reading text", "translate": "Translating text", "more": "Searching for alternatives"}

# UI wording is concise; diagnostics retain the detailed English message above.
UI_MESSAGES = {
    "sentence_language": "This route needs an unsupported sentence language. Choose another language pair.",
    "sentence_split": "Sentence splitting failed. Select a shorter passage and check required files.",
    "missing_pack": "A language pack is missing or changed. Download it in Settings.",
    "pack_restart": "A language pack changed. Restart Language Lens.",
    "pack_platform": "This pack requires Windows x64. Use the portable release.",
    "disk_full": "Disk full. Free space and retry.",
    "permission": "Access denied. Check folder permissions and retry.",
    "network": "Download connection failed. Check your connection and retry.",
    "timeout": "Task timed out. Retry or select a shorter passage.",
    "route_unavailable": "No downloadable route is available. Choose another language pair.",
    "missing_assets": "Local files are missing or changed. Check required files in Settings.",
    "integrity": "File verification failed. Retry the download; installed models are retained.",
    "execution": "The local task failed. Retry, check required files in Settings, or open diagnostics.",
    "runtime": "A required local component could not be loaded.",
    "inspection": "Installation status is unknown because the check failed. No local files were removed.",
}


def failure_from_code(code: str, command: str, stage: str | None = None) -> Failure:
    prefix = STAGES.get(command, "Local task")
    return Failure(code, stage or command, f"{prefix}: {MESSAGES[code]}")


def describe_failure(exception: BaseException, command: str, stage: str | None = None) -> Failure:
    from language_lens.services.translation import ModelRouteUnavailable
    chain, seen = [], set()
    current = exception
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    code = "inspection" if command == "status" else "execution"
    for item in reversed(chain):
        if isinstance(item, KnownTaskError) and item.code in MESSAGES:
            code = item.code
        elif isinstance(item, ModelRouteUnavailable):
            code = "route_unavailable"
        elif isinstance(item, PermissionError) or getattr(item, "errno", None) in (errno.EACCES, errno.EPERM):
            code = "permission"
        elif isinstance(item, OSError) and item.errno == errno.ENOSPC:
            code = "disk_full"
        elif isinstance(item, (HTTPError, URLError, ConnectionError)):
            code = "network"
        elif isinstance(item, TimeoutError):
            code = "timeout"
        elif isinstance(item, ImportError):
            code = "runtime"
    return failure_from_code(code, command, stage)
