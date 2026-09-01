#!/usr/bin/env python3
"""Generate "Night Check-in v2" — posts DIRECTLY to the new spine (ingest_capture)
with the same checkin payload shape the extractor reads. No old-system token.

Asks: Mood, Stress, Mental sharpness, Energy, Day rating (0-10 numbers), a note,
and food (comma-separated, blank ok) -> two POSTs: the check-in, then the food.
Output: /tmp/NightV2_unsigned.shortcut
"""
import plistlib
import uuid

URL = "https://cykviouklidnbsbgdgdo.supabase.co/rest/v1/rpc/ingest_capture"
ANON = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN5a3Zpb3VrbGlkbmJzYmdkZ2RvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM5NzA0MzYsImV4cCI6MjA5OTU0NjQzNn0."
        "0YqUtrBMQ-6LOOIGLCj6UcqelccV2WdNVNrbEArGnk0")

U = lambda: str(uuid.uuid4()).upper()

def token(out_uuid, out_name):
    return {"Value": {"OutputUUID": out_uuid, "Type": "ActionOutput", "OutputName": out_name},
            "WFSerializationType": "WFTextTokenAttachment"}

def token_string(out_uuid, out_name):
    return {"Value": {"string": "￼",
                      "attachmentsByRange": {"{0, 1}": {"OutputUUID": out_uuid,
                                                        "Type": "ActionOutput",
                                                        "OutputName": out_name}}},
            "WFSerializationType": "WFTextTokenString"}

def literal(s):
    return {"Value": {"string": s, "attachmentsByRange": {}},
            "WFSerializationType": "WFTextTokenString"}

def item(key, val, t=0):
    return {"WFItemType": t,
            "WFKey": literal(key),
            "WFValue": val}

def ask_number(u, prompt):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.ask",
            "WFWorkflowActionParameters": {"UUID": u, "WFAskActionPrompt": prompt,
                                           "WFInputType": "Number"}}

def ask_text(u, prompt):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.ask",
            "WFWorkflowActionParameters": {"UUID": u, "WFAskActionPrompt": prompt,
                                           "WFInputType": "Text",
                                           "WFAskActionDefaultAnswer": ""}}

mood, stress, sharp, energy, rating = U(), U(), U(), U(), U()
note, food, date_u, fmt = U(), U(), U(), U()

# number answers ride as text-token strings; the server casts jsonb -> numeric,
# and the extractor float()s them — a numeric string is fine.
scores = [item("mood", token_string(mood, "Provided Input")),
          item("stress", token_string(stress, "Provided Input")),
          item("mental_sharpness", token_string(sharp, "Provided Input")),
          item("energy", token_string(energy, "Provided Input")),
          item("day_rating", token_string(rating, "Provided Input"))]

headers = {"Value": {"WFDictionaryFieldValueItems": [
                item("apikey", literal(ANON)),
                item("Authorization", literal("Bearer " + ANON)),
                item("Content-Type", literal("application/json"))]},
           "WFSerializationType": "WFDictionaryFieldValue"}

def post(body_items):
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
            "WFWorkflowActionParameters": {
                "ShowHeaders": True, "WFURL": URL, "WFHTTPMethod": "POST",
                "WFHTTPHeaders": headers, "WFHTTPBodyType": "JSON",
                "WFJSONValues": {"Value": {"WFDictionaryFieldValueItems": body_items},
                                 "WFSerializationType": "WFDictionaryFieldValue"}}}

actions = [
    ask_number(mood,   "Mood (0-10)"),
    ask_number(stress, "Stress (0-10)"),
    ask_number(sharp,  "Mental sharpness (0-10)"),
    ask_number(energy, "Energy (0-10)"),
    ask_number(rating, "Day rating (0-10)"),
    ask_text(note, "Anything to note about today?"),
    ask_text(food, "What did you eat/drink today? (comma-separated; blank if logged)"),
    {"WFWorkflowActionIdentifier": "is.workflow.actions.date",
     "WFWorkflowActionParameters": {"UUID": date_u, "WFDateActionMode": "Current Date"}},
    {"WFWorkflowActionIdentifier": "is.workflow.actions.format.date",
     "WFWorkflowActionParameters": {"UUID": fmt, "WFDateFormatStyle": "Custom",
                                    "WFDateFormat": "yyyy-MM-dd'T'HH:mm:ssZZZZZ",
                                    "WFInput": token(date_u, "Current Date")}},
    post([item("p_source", literal("shortcut_text")),
          item("p_captured_at", token_string(fmt, "Formatted Date")),
          item("p_payload",
               {"Value": {"WFDictionaryFieldValueItems":
                    [item("kind", literal("checkin")),
                     item("type", literal("night"))] + scores +
                    [item("note", token_string(note, "Provided Input"))]},
                "WFSerializationType": "WFDictionaryFieldValue"}, t=1)]),
    post([item("p_source", literal("shortcut_text")),
          item("p_captured_at", token_string(fmt, "Formatted Date")),
          item("p_payload",
               {"Value": {"WFDictionaryFieldValueItems":
                    [item("kind", literal("food")),
                     item("text", token_string(food, "Provided Input"))]},
                "WFSerializationType": "WFDictionaryFieldValue"}, t=1)]),
    {"WFWorkflowActionIdentifier": "is.workflow.actions.shownotification",
     "WFWorkflowActionParameters": {"WFNotificationActionBody": "Night check-in ✓",
                                    "WFNotificationActionTitle": "Personal OS"}},
]

wf = {"WFWorkflowMinimumClientVersion": 900,
      "WFWorkflowMinimumClientVersionString": "900",
      "WFWorkflowClientVersion": "2605.0.5",
      "WFWorkflowHasOutputFallback": False,
      "WFWorkflowHasShortcutInputVariables": False,
      "WFWorkflowIcon": {"WFWorkflowIconStartColor": 946986751,
                         "WFWorkflowIconGlyphNumber": 59772},
      "WFWorkflowImportQuestions": [],
      "WFWorkflowInputContentItemClasses": [],
      "WFWorkflowTypes": ["NCWidget", "WatchKit"],
      "WFWorkflowActions": actions}

out = "/tmp/NightV2_unsigned.shortcut"
with open(out, "wb") as f:
    plistlib.dump(wf, f)
print("wrote", out)
