# Step 1a — DynamoDB (the data layer)

**Date:** 2026-10-16 · **Region:** `eu-central-1` · **Status:** ✅ ACTIVE

---

## 🎯 Goal of this step

Create the table that stores all expenses — the **source of truth** for the application.

## ⚙️ What was created

```bash
aws dynamodb create-table \
  --table-name expense-tracker-expenses \
  --attribute-definitions AttributeName=userId,AttributeType=S AttributeName=expenseId,AttributeType=S \
  --key-schema AttributeName=userId,KeyType=HASH AttributeName=expenseId,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=expense-tracker Key=Owner,Value=cijo
```

**Result:**

| Property | Value |
|---|---|
| Table name | `expense-tracker-expenses` |
| Status | `ACTIVE` |
| Partition key (HASH) | `userId` (String) |
| Sort key (RANGE) | `expenseId` (String) |
| Billing mode | `PAY_PER_REQUEST` (on-demand) |
| ARN | `arn:aws:dynamodb:eu-central-1:896618135736:table/expense-tracker-expenses` |
| Tags | `Project=expense-tracker`, `Owner=cijo` |

## 📊 Where it sits

```
   API Gateway  ──►  Lambda  ──►  ┌──────────────────────────────┐
   (JWT)             (Python)     │        DYNAMODB              │
                                  │  table: expense-tracker-     │
                                  │         expenses             │
                                  │                              │
                                  │  PK  userId     ← tenant ID  │
                                  │  SK  expenseId  ← unique     │
                                  │                              │
                                  │  item: { amount, currency,   │
                                  │          category, date,     │
                                  │          note, receiptKey }  │
                                  └──────────────────────────────┘
```

## 🧠 Key concepts learned

| Concept | Meaning here |
|---|---|
| **Partition key (HASH)** | `userId` — decides which partition the item lives in. Also our **tenant boundary**. |
| **Sort key (RANGE)** | `expenseId` — makes items unique within a partition; enables range/prefix queries. |
| **Composite primary key** | `(userId, expenseId)` must be unique; same `expenseId` may exist under different users. |
| **On-demand billing** | Pay per request; no RCU/WCU provisioning; ideal for spiky, unknown traffic. |
| **Query vs Scan** | `Query` needs a key condition (efficient); `Scan` reads everything (expensive). |
| **Item** | DynamoDB's row — a set of attributes; each attribute is typed (`S`, `N`, `BOOL`, `L`, ...). |

## ⚖️ Why DynamoDB (vs alternatives)

| Alternative | Why not |
|---|---|
| RDS / Aurora PostgreSQL | Always-on cost; relational overkill for key lookups |
| S3 | Object storage; cannot query individual items |
| ElastiCache | A cache, not durable storage |
| DocumentDB | MongoDB-compatible; no need for that compatibility |

## 🔬 Drills — touch the service yourself

```bash
# insert an item by hand
aws dynamodb put-item --table-name expense-tracker-expenses --item \
 '{"userId":{"S":"test-user"},"expenseId":{"S":"exp-001"},"amount":{"N":"250"},"category":{"S":"food"},"date":{"S":"2026-10-16"}}'

# read by primary key
aws dynamodb get-item --table-name expense-tracker-expenses \
 --key '{"userId":{"S":"test-user"},"expenseId":{"S":"exp-001"}}'

# query by partition key (the correct way to fetch many items)
aws dynamodb query --table-name expense-tracker-expenses \
 --key-condition-expression 'userId = :u' \
 --expression-attribute-values '{":u":{"S":"test-user"}}'

# clean up
aws dynamodb delete-item --table-name expense-tracker-expenses \
 --key '{"userId":{"S":"test-user"},"expenseId":{"S":"exp-001"}}'
```

**Console:** `https://eu-central-1.console.aws.amazon.com/dynamodbv2/home?region=eu-central-1#table?name=expense-tracker-expenses`

## 🎯 Interview questions this unlocks

1. Partition key vs sort key — what does each solve?
2. On-demand vs provisioned capacity — cost/performance trade-offs?
3. How do you enforce **tenant isolation** in DynamoDB? *(→ set the PK from the authenticated JWT subject)*
4. What is a **hot partition** and why is `userId` a mild risk? *(→ a single heavy user; mitigation: write sharding / composite PK)*
5. Query vs Scan — and why is Scan a red flag in production?
6. When would you choose **RDS instead** of DynamoDB? *(→ relational integrity, joins, ad-hoc SQL, transactions across entities)*
7. What happens at scale — how does DynamoDB partition data? *(→ hash of PK → partitions; adaptive capacity)*

## 💰 Cost

- On-demand: first 25 GB storage + a monthly allowance of read/write requests free (Free Tier).
- This table sits **far** inside Free Tier for a portfolio workload.

## ⏭️ Next

**Step 1b — S3 bucket** for receipt files (private bucket, presigned URLs, CORS).
