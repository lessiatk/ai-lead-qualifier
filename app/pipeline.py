"""Lead -> qualify -> store -> alert. Framework-agnostic so it is easy to test and reuse."""
from __future__ import annotations

import logging

from .config import Settings
from .models import Lead, Priority, QualifiedLead
from .notifier import TelegramNotifier, build_notifier, format_alert
from .qualifier import Qualifier, build_qualifier
from .sinks import Sink, build_sinks

log = logging.getLogger(__name__)


class LeadPipeline:
    def __init__(self, qualifier: Qualifier, sinks: list[Sink], notifier: TelegramNotifier, hot_threshold: int = 70):
        self.qualifier = qualifier
        self.sinks = sinks
        self.notifier = notifier
        self.hot_threshold = hot_threshold

    @classmethod
    def from_settings(cls, settings: Settings) -> "LeadPipeline":
        return cls(build_qualifier(settings), build_sinks(settings), build_notifier(settings), settings.hot_threshold)

    def process(self, lead: Lead) -> QualifiedLead:
        qualification = self.qualifier.qualify(lead)
        item = QualifiedLead(lead=lead, qualification=qualification, provider=self.qualifier.name)

        for sink in self.sinks:
            try:
                sink.save(item)
            except Exception as exc:
                log.error("Sink %s failed: %s", type(sink).__name__, exc)

        if qualification.priority == Priority.hot or qualification.score >= self.hot_threshold:
            self.notifier.send(format_alert(item))

        log.debug("Lead %s -> %s (%s)", lead.email, qualification.priority.value, qualification.score)
        return item
