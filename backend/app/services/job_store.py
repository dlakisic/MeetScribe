from datetime import datetime


class JobStore:
    """In-memory store for tracking background job statuses."""

    def __init__(self):
        self._jobs: dict[str, dict] = {}

    def create_job(self, job_id: str, meeting_id: int):
        self._jobs[job_id] = {
            "status": "queued",
            "meeting_id": meeting_id,
            "created_at": datetime.now().isoformat(),
        }

    def update_status(
        self, job_id: str, status: str, result: dict | None = None, error: str | None = None
    ):
        if job_id not in self._jobs:
            return

        self._jobs[job_id]["status"] = status
        if result:
            self._jobs[job_id]["result"] = result
        if error:
            self._jobs[job_id]["error"] = error

    def get_job(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)
