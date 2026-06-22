from __future__ import annotations

class CrmClassifierService:
    # Keywords for stage classification
    NOT_INTERESTED_KEYWORDS = ["no interes", "no le interes", "no quiere", "not interest", "declin", "reject"]
    QUALIFIED_KEYWORDS = ["interes", "cualific", "calific", "cotiz", "propuest", "qualif", "price", "cotizar"]

    def classify_lead_stage(
        self,
        call_status: str | None,
        summary: str | None,
        short_summary: str | None,
    ) -> str | None:
        if call_status == "voicemail":
            return "follow_up"
        if call_status == "unanswered":
            return "follow_up"

        # Merge summary and short summary for checking keywords
        text = " ".join(filter(None, [summary, short_summary])).lower()
        if not text:
            return None

        # Check for not interested / lost
        if any(kw in text for kw in self.NOT_INTERESTED_KEYWORDS):
            return "not_interested"

        # Check for qualified interest
        if any(kw in text for kw in self.QUALIFIED_KEYWORDS):
            return "qualified"

        return None
