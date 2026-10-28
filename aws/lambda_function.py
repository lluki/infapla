"""
AWS Lambda Function for Amazon Alexa Shopping List Integration with InFaPla.

Supports two modes in a single Lambda:
1. Alexa Skills Kit (ASK) Custom Skill:
   - Voice trigger: "Alexa, tell Family Planner to add [items]"
   - Saves spoken items to DynamoDB (table: 'infapla-alexa-shopping').
2. HTTPS Function URL / API Gateway endpoint:
   - GET: Fetches pending shopping items for InFaPla.
   - POST / DELETE: Clears the processed items after InFaPla imports them.
   - Optional header authentication: 'x-api-key' or 'Authorization: Bearer <secret>'.
"""

import os
import json
import uuid
import datetime
import boto3

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "infapla-alexa-shopping")
SYNC_SECRET = os.environ.get("SYNC_SECRET", "")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def lambda_handler(event, context):
    # Check if this is an Alexa Skills Kit event
    if "request" in event and "session" in event:
        return handle_alexa_skill_request(event)

    # Otherwise, handle as HTTP request (Lambda Function URL or API Gateway)
    return handle_http_request(event)


# ==============================================================================
# 1. Alexa Skills Kit Request Handler
# ==============================================================================

def handle_alexa_skill_request(event):
    request = event.get("request", {})
    req_type = request.get("type")

    if req_type == "LaunchRequest":
        return build_alexa_response(
            speech="Welcome to Family Shopping List. What items would you like to add?",
            should_end_session=False
        )

    elif req_type == "IntentRequest":
        intent = request.get("intent", {})
        intent_name = intent.get("name")

        if intent_name == "AddShoppingItemIntent":
            slots = intent.get("slots", {})
            item_slot = slots.get("items", {})
            raw_items = item_slot.get("value", "").strip()

            if not raw_items:
                return build_alexa_response(
                    speech="I didn't catch the items. What should I add to the shopping list?",
                    should_end_session=False
                )

            # Store in DynamoDB
            item_id = str(uuid.uuid4())
            timestamp = datetime.datetime.utcnow().isoformat()
            
            table.put_item(
                Item={
                    "id": item_id,
                    "text": raw_items,
                    "timestamp": timestamp,
                    "status": "pending"
                }
            )

            speech_output = f"Added {raw_items} to your shopping list."
            return build_alexa_response(speech=speech_output, should_end_session=True)

        elif intent_name in ("AMAZON.HelpIntent",):
            return build_alexa_response(
                speech="You can say: add milk and eggs to shopping list. What would you like to add?",
                should_end_session=False
            )

        elif intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            return build_alexa_response(speech="Goodbye!", should_end_session=True)

    elif req_type == "SessionEndedRequest":
        return build_alexa_response(speech="", should_end_session=True)

    return build_alexa_response(speech="I'm not sure how to help with that.", should_end_session=True)


def build_alexa_response(speech: str, should_end_session: bool = True):
    response = {
        "version": "1.0",
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": speech
            },
            "shouldEndSession": should_end_session
        }
    }
    if not should_end_session:
        response["response"]["reprompt"] = {
            "outputSpeech": {
                "type": "PlainText",
                "text": "What items would you like to add?"
            }
        }
    return response


# ==============================================================================
# 2. HTTP / Lambda Function URL Handler (for InFaPla periodic sync)
# ==============================================================================

def handle_http_request(event):
    headers = event.get("headers", {}) or {}
    # Lowercase header keys for easy lookup
    lc_headers = {k.lower(): v for k, v in headers.items()}

    # Verify secret token if configured
    if SYNC_SECRET:
        req_token = lc_headers.get("x-api-key")
        auth_hdr = lc_headers.get("authorization", "")
        if auth_hdr.startswith("Bearer "):
            req_token = auth_hdr[7:].strip()

        if req_token != SYNC_SECRET:
            return {
                "statusCode": 401,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Unauthorized: invalid or missing sync secret"})
            }

    http_method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "GET"
    ).upper()

    # GET: Return all pending items
    if http_method == "GET":
        try:
            res = table.scan()
            items = res.get("Items", [])
            pending = [
                {"id": i["id"], "text": i.get("text", ""), "timestamp": i.get("timestamp")}
                for i in items
                if i.get("status") in (None, "", "pending")
            ]
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"items": pending})
            }
        except Exception as e:
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": str(e)})
            }

    # POST or DELETE: Clear items by ID
    elif http_method in ("POST", "DELETE"):
        body_str = event.get("body", "{}") or "{}"
        try:
            data = json.loads(body_str)
        except Exception:
            data = {}

        ids_to_clear = data.get("ids", [])
        cleared_count = 0
        for item_id in ids_to_clear:
            try:
                table.delete_item(Key={"id": item_id})
                cleared_count += 1
            except Exception:
                pass

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"success": True, "cleared_count": cleared_count})
        }

    return {
        "statusCode": 405,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": f"Method {http_method} not allowed"})
    }
