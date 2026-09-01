#!/usr/bin/env python3
"""Generate the "Log Food" iOS/macOS shortcut as a signable .shortcut plist.

Actions: Ask for Input (text) -> Current Date -> Format Date (ISO 8601)
         -> POST /rest/v1/rpc/ingest_capture  {kind:'food', text:<input>}
The anon key is embedded (public-by-design; the server side is write-only).
Output: /tmp/LogFood_unsigned.shortcut  (then: shortcuts sign; open)
"""
import plistlib
import sys
import uuid

URL = "https://cykviouklidnbsbgdgdo.supabase.co/rest/v1/rpc/ingest_capture"
ANON = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN5a3Zpb3VrbGlkbmJzYmdkZ2RvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM5NzA0MzYsImV4cCI6MjA5OTU0NjQzNn0."
        "0YqUtrBMQ-6LOOIGLCj6UcqelccV2WdNVNrbEArGnk0")

ask_uuid = str(uuid.uuid4()).upper()
date_uuid = str(uuid.uuid4()).upper()
fmt_uuid = str(uuid.uuid4()).upper()

def token(out_uuid, out_name):
    """A bare attachment token (whole-value = an action output)."""
    return {"Value": {"OutputUUID": out_uuid, "Type": "ActionOutput",
                      "OutputName": out_name},
            "WFSerializationType": "WFTextTokenAttachment"}

def token_string(out_uuid, out_name):
    """A text-token string whose entire content is one attachment."""
    return {"Value": {"string": "￼",
                      "attachmentsByRange": {
                          "{0, 1}": {"OutputUUID": out_uuid, "Type": "ActionOutput",
                                     "OutputName": out_name}}},
            "WFSerializationType": "WFTextTokenString"}

def text_item(key, value_serialized, item_type=0):
    return {"WFItemType": item_type,
            "WFKey": {"Value": {"string": key, "attachmentsByRange": {}},
                      "WFSerializationType": "WFTextTokenString"},
            "WFValue": value_serialized}

def literal(s):
    return {"Value": {"string": s, "attachmentsByRange": {}},
            "WFSerializationType": "WFTextTokenString"}

actions = [
    {"WFWorkflowActionIdentifier": "is.workflow.actions.ask",
     "WFWorkflowActionParameters": {
         "UUID": ask_uuid,
         "WFAskActionPrompt": "What did you eat/drink? (comma-separate items)",
         "WFInputType": "Text"}},
    {"WFWorkflowActionIdentifier": "is.workflow.actions.date",
     "WFWorkflowActionParameters": {
         "UUID": date_uuid,
         "WFDateActionMode": "Current Date"}},
    {"WFWorkflowActionIdentifier": "is.workflow.actions.format.date",
     "WFWorkflowActionParameters": {
         "UUID": fmt_uuid,
         "WFDateFormatStyle": "Custom",
         "WFDateFormat": "yyyy-MM-dd'T'HH:mm:ssZZZZZ",
         "WFInput": token(date_uuid, "Current Date")}},
    {"WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
     "WFWorkflowActionParameters": {
         "ShowHeaders": True,
         "WFURL": URL,
         "WFHTTPMethod": "POST",
         "WFHTTPHeaders": {
             "Value": {"WFDictionaryFieldValueItems": [
                 text_item("apikey", literal(ANON)),
                 text_item("Authorization", literal("Bearer " + ANON)),
                 text_item("Content-Type", literal("application/json"))]},
             "WFSerializationType": "WFDictionaryFieldValue"},
         "WFHTTPBodyType": "JSON",
         "WFJSONValues": {
             "Value": {"WFDictionaryFieldValueItems": [
                 text_item("p_source", literal("shortcut_text")),
                 text_item("p_captured_at",
                           token_string(fmt_uuid, "Formatted Date")),
                 text_item("p_payload",
                           {"Value": {"WFDictionaryFieldValueItems": [
                                text_item("kind", literal("food")),
                                text_item("text",
                                          token_string(ask_uuid, "Provided Input"))]},
                            "WFSerializationType": "WFDictionaryFieldValue"},
                           item_type=1)]},
             "WFSerializationType": "WFDictionaryFieldValue"}}},
    {"WFWorkflowActionIdentifier": "is.workflow.actions.shownotification",
     "WFWorkflowActionParameters": {
         "WFNotificationActionBody": "Logged ✓",
         "WFNotificationActionTitle": "Personal OS"}},
]

wf = {
    "WFWorkflowMinimumClientVersion": 900,
    "WFWorkflowMinimumClientVersionString": "900",
    "WFWorkflowClientVersion": "2605.0.5",
    "WFWorkflowHasOutputFallback": False,
    "WFWorkflowHasShortcutInputVariables": False,
    "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4274264319,
                       "WFWorkflowIconGlyphNumber": 61440},
    "WFWorkflowImportQuestions": [],
    "WFWorkflowInputContentItemClasses": [],
    "WFWorkflowTypes": ["NCWidget", "WatchKit"],
    "WFWorkflowActions": actions,
}

out = "/tmp/LogFood_unsigned.shortcut"
with open(out, "wb") as f:
    plistlib.dump(wf, f)
print("wrote", out)
