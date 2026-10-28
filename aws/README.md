# Amazon Alexa & AWS Integration for InFaPla

This guide walks you through connecting your Amazon Alexa to InFaPla so that spoken shopping list items are automatically fetched, parsed into distinct items via an AI model, inserted into InFaPla's `shopping/list.md`, and cleared from Alexa once successfully imported.

---

## 1. Architectural Overview & Context

> **Note on Amazon's API Change (July 1, 2024):**  
> Amazon deprecated and shut down the legacy 3rd-party "Alexa Household List Management API". Direct REST scraping of the native Amazon shopping list by external developer skills is no longer supported by Amazon.
> 
> The official, robust, and permanent architecture is a **Custom Alexa Skill backed by AWS Lambda & DynamoDB**.

### How It Works:
```
┌─────────────────┐       ┌──────────────────────┐       ┌────────────────────────┐
│ Amazon Alexa    │       │ AWS Lambda           │       │ AWS DynamoDB           │
│ Echo / Mobile   │ ────> │ (Alexa Skill Handler │ ────> │ Table:                 │
│ "Add milk & tea"│ (ASK) │  + Function URL)     │       │ infapla-alexa-shopping │
└─────────────────┘       └──────────────────────┘       └──────────┬─────────────┘
                                                                    │
                                                                    │ (Periodic Poll & Clear)
                                                                    ▼
                                                         ┌────────────────────────┐
                                                         │ InFaPla Daemon         │
                                                         │ (Periodic Task)        │
                                                         │   1. Fetch from AWS    │
                                                         │   2. Filter via Model  │
                                                         │   3. Add to list.md    │
                                                         │   4. Clear AWS List    │
                                                         └────────────────────────┘
```

---

## 2. Step-by-Step AWS Setup Walkthrough

### Step 1: Create the DynamoDB Table
1. Open the [AWS DynamoDB Console](https://console.aws.amazon.com/dynamodb/).
2. Click **Create table**.
3. **Table name**: `infapla-alexa-shopping`
4. **Partition key**: `id` (Type: `String`)
5. Table settings: **Default settings** (On-Demand capacity to stay within free tier).
6. Click **Create table**.

---

### Step 2: Create the AWS Lambda Function
1. Open the [AWS Lambda Console](https://console.aws.amazon.com/lambda/).
2. Click **Create function** -> **Author from scratch**.
3. **Function name**: `InFaPla-AlexaShopping`
4. **Runtime**: **Python 3.11** or **Python 3.12**.
5. **Architecture**: `x86_64` or `arm64`.
6. Under **Change default execution role**, ensure the role has permission to access DynamoDB:
   - In IAM, attach the policy `AmazonDynamoDBFullAccess` (or create a custom inline policy scoping `dynamodb:PutItem`, `dynamodb:Scan`, `dynamodb:DeleteItem` to `infapla-alexa-shopping`).
7. Click **Create function**.
8. Paste the code from [`aws/lambda_function.py`](./lambda_function.py) into `lambda_function.py` in the Lambda code editor and click **Deploy**.
9. Under **Configuration** -> **Environment variables**, set:
   - `DYNAMODB_TABLE`: `infapla-alexa-shopping`
   - `SYNC_SECRET`: `<Choose-A-Random-Secret-Token>` (e.g. `my-infapla-secure-sync-token`)

---

### Step 3: Enable Lambda Function URL (Zero-Configuration HTTPS Access)
Lambda Function URLs provide a dedicated HTTPS endpoint directly without needing API Gateway:
1. In your Lambda function, open the **Configuration** tab.
2. Select **Function URL** from the left sidebar and click **Create function URL**.
3. **Auth type**: `NONE` (authentication is handled securely in code using your `SYNC_SECRET` via the `x-api-key` header).
4. Click **Save**.
5. Copy your **Function URL** (e.g. `https://abcdef123456.lambda-url.us-east-1.on.aws/`).

---

### Step 4: Create the Alexa Skill in Alexa Developer Console
1. Go to the [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask).
2. Click **Create Skill**.
3. **Skill name**: `Family Planner` (or `InFaPla` / `Shopping List`).
4. **Primary locale**: Your primary language (e.g. English (US) or English (UK)).
5. **Model to add**: **Custom**.
6. **Hosting service**: **Provision your own** (since AWS Lambda hosts the backend).
7. Click **Create Skill**.
8. In the left sidebar:
   - Go to **Interaction Model** -> **JSON Editor**.
   - Paste the contents of [`aws/skill_model.json`](./skill_model.json).
   - Click **Save Model** and then **Build Model**.
9. In the left sidebar, click **Endpoint**:
   - Select **AWS Lambda ARN**.
   - Copy your Skill ID (e.g. `amzn1.ask.skill.xxxx`).
   - In the **Default Region** field, paste your Lambda function ARN (from Step 2).
   - Click **Save Endpoints**.
10. Go back to your AWS Lambda Console:
    - Under **Function overview**, click **Add trigger**.
    - Select **Alexa Skills Kit**.
    - Under **Skill ID verification**, choose **Enable** and paste the Skill ID from step 9.
    - Click **Add**.

---

### Step 5: (Optional) Create an Alexa Voice Routine for Natural Phrasing
If you prefer saying *"Alexa, add milk to shopping list"* instead of invoking the skill by name (*"Alexa, tell Family Planner to add milk"*):
1. Open the **Amazon Alexa App** on your phone.
2. Go to **More** -> **Routines** -> **+** (Create Routine).
3. **When this happens**: Voice -> *"add to family shopping list"* or *"shopping list"*.
4. **Add action**: **Custom** -> *"ask Family Planner to add"*.
5. Save the routine.

---

## 3. Configuring InFaPla

Configure InFaPla to poll AWS periodically. You have two options:

### Option A: Via Lambda Function URL (Recommended, Zero Dependencies)
Run InFaPla with:
```bash
python3 main.py \
  --dir ./data \
  --alexa-url "https://abcdef123456.lambda-url.us-east-1.on.aws/" \
  --alexa-secret "my-infapla-secure-sync-token" \
  --alexa-interval 60
```
Or via environment variables:
```bash
export ALEXA_SYNC_URL="https://abcdef123456.lambda-url.us-east-1.on.aws/"
export ALEXA_SYNC_SECRET="my-infapla-secure-sync-token"
export INFAPLA_ALEXA_INTERVAL="60"
python3 main.py --dir ./data
```

### Option B: Direct AWS DynamoDB Sync (boto3)
If you prefer direct AWS IAM credentials:
```bash
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-1"
export ALEXA_DYNAMODB_TABLE="infapla-alexa-shopping"
export INFAPLA_ALEXA_INTERVAL="60"
python3 main.py --dir ./data
```

---

## 4. Verification & Testing

1. Speak to Alexa: *"Alexa, tell Family Planner to add bananas, 2 cartons of milk, and dish soap."*
2. Alexa confirms: *"Added bananas, 2 cartons of milk, and dish soap to your shopping list."*
3. Within 60 seconds (or immediately via `curl -X POST http://localhost:8080/api/alexa/sync`):
   - InFaPla fetches the raw utterance.
   - The AI model processes it with:
     > *"Add only items to shopping list. Each item of input shopping list may contain items that are in fact multiple items. parse them and add them as separat items."*
   - InFaPla splits and inserts them into `shopping/list.md`:
     - `- [ ] Bananas`
     - `- [ ] 2 cartons of milk`
     - `- [ ] Dish soap`
   - InFaPla issues a clear request to AWS, wiping the items from DynamoDB.
