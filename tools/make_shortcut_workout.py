#!/usr/bin/env python3
"""Generate "Log Workout" — one SET per run (REQ-ONT-017 per-set granularity):
exercise, weight (lb), reps, RPE -> POST ingest_capture {kind:'workout', ...}.
The capture is immutable; atom-shape extraction follows OQ-33's ruling.
Output: /tmp/LogWorkout_unsigned.shortcut
"""
import plistlib
import uuid

URL = "https://cykviouklidnbsbgdgdo.supabase.co/rest/v1/rpc/ingest_capture"
ANON = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN5a3Zpb3VrbGlkbmJzYmdkZ2RvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM5NzA0MzYsImV4cCI6MjA5OTU0NjQzNn0."
        "0YqUtrBMQ-6LOOIGLCj6UcqelccV2WdNVNrbEArGnk0")
U = lambda: str(uuid.uuid4()).upper()

def token(ou, on):
    return {"Value": {"OutputUUID": ou, "Type": "ActionOutput", "OutputName": on},
            "WFSerializationType": "WFTextTokenAttachment"}
def tstr(ou, on):
    return {"Value": {"string": "￼", "attachmentsByRange":
            {"{0, 1}": {"OutputUUID": ou, "Type": "ActionOutput", "OutputName": on}}},
            "WFSerializationType": "WFTextTokenString"}
def lit(s):
    return {"Value": {"string": s, "attachmentsByRange": {}},
            "WFSerializationType": "WFTextTokenString"}
def item(k, v, t=0):
    return {"WFItemType": t, "WFKey": lit(k), "WFValue": v}
def ask(u, prompt, typ):
    p = {"UUID": u, "WFAskActionPrompt": prompt, "WFInputType": typ}
    if typ == "Text": p["WFAskActionDefaultAnswer"] = ""
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.ask",
            "WFWorkflowActionParameters": p}

ex, wt, reps, rpe, date_u, fmt = U(), U(), U(), U(), U(), U()
actions = [
    ask(ex,   "Exercise?", "Text"),
    ask(wt,   "Weight (lb) — 0 if bodyweight", "Number"),
    ask(reps, "Reps?", "Number"),
    ask(rpe,  "RPE (0-10)?", "Number"),
    {"WFWorkflowActionIdentifier": "is.workflow.actions.date",
     "WFWorkflowActionParameters": {"UUID": date_u, "WFDateActionMode": "Current Date"}},
    {"WFWorkflowActionIdentifier": "is.workflow.actions.format.date",
     "WFWorkflowActionParameters": {"UUID": fmt, "WFDateFormatStyle": "Custom",
                                    "WFDateFormat": "yyyy-MM-dd'T'HH:mm:ssZZZZZ",
                                    "WFInput": token(date_u, "Current Date")}},
    {"WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
     "WFWorkflowActionParameters": {
        "ShowHeaders": True, "WFURL": URL, "WFHTTPMethod": "POST",
        "WFHTTPHeaders": {"Value": {"WFDictionaryFieldValueItems": [
            item("apikey", lit(ANON)),
            item("Authorization", lit("Bearer " + ANON)),
            item("Content-Type", lit("application/json"))]},
            "WFSerializationType": "WFDictionaryFieldValue"},
        "WFHTTPBodyType": "JSON",
        "WFJSONValues": {"Value": {"WFDictionaryFieldValueItems": [
            item("p_source", lit("shortcut_text")),
            item("p_captured_at", tstr(fmt, "Formatted Date")),
            item("p_payload", {"Value": {"WFDictionaryFieldValueItems": [
                item("kind", lit("workout")),
                item("exercise", tstr(ex, "Provided Input")),
                item("weight_lb", tstr(wt, "Provided Input")),
                item("reps", tstr(reps, "Provided Input")),
                item("rpe", tstr(rpe, "Provided Input"))]},
                "WFSerializationType": "WFDictionaryFieldValue"}, t=1)]},
            "WFSerializationType": "WFDictionaryFieldValue"}}},
    {"WFWorkflowActionIdentifier": "is.workflow.actions.shownotification",
     "WFWorkflowActionParameters": {"WFNotificationActionBody": "Set logged ✓",
                                    "WFNotificationActionTitle": "Personal OS"}},
]
wf = {"WFWorkflowMinimumClientVersion": 900,
      "WFWorkflowMinimumClientVersionString": "900",
      "WFWorkflowClientVersion": "2605.0.5",
      "WFWorkflowHasOutputFallback": False,
      "WFWorkflowHasShortcutInputVariables": False,
      "WFWorkflowIcon": {"WFWorkflowIconStartColor": 431817727,
                         "WFWorkflowIconGlyphNumber": 61554},
      "WFWorkflowImportQuestions": [],
      "WFWorkflowInputContentItemClasses": [],
      "WFWorkflowTypes": ["NCWidget", "WatchKit"],
      "WFWorkflowActions": actions}
with open("/tmp/LogWorkout_unsigned.shortcut", "wb") as f:
    plistlib.dump(wf, f)
print("wrote /tmp/LogWorkout_unsigned.shortcut")
