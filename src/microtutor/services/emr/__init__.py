"""EMR note extraction service (structured clinical documentation)."""

from .service import EmrNotesService, get_emr_service

__all__ = ["EmrNotesService", "get_emr_service"]
