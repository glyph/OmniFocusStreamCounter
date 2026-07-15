from datetype import DateTime

from oftypes import AppScriptExpression, SomeTask

def expression(
    what: SomeTask, today: DateTime[None], tomorrow: DateTime[None]
) -> AppScriptExpression:
    return (
        (what.effective_due_date < tomorrow)
        .OR(what.effective_planned_date < tomorrow)
        .AND(what.effectively_completed == False)
        .AND(what.effectively_dropped == False)
    ).OR((what.completion_date >= today).OR((what.dropped_date >= today)))


