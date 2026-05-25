from flask import Flask, render_template, request, jsonify, send_from_directory
import re
import json
from datetime import datetime
import gspread
import google.generativeai as genai
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# =========================
# GEMINI
# =========================
genai.configure(api_key="AIzaSyB3yGnqmtiRMT3OPb6Aeu7vAWqcxR55X0c")
model = genai.GenerativeModel("gemini-2.5-flash")

# =========================
# GOOGLE SHEET
# =========================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    "credentials.json",
    scopes=scope
)

client = gspread.authorize(creds)

sheet = client.open("Expense Sheet")
data_sheet = sheet.worksheet("data")
memory_sheet = sheet.worksheet("memory")

# =========================
# TEXT NORMALIZER
# =========================
COMMON_FIXES = {
    "expese": "expense",
    "expnse": "expense",
    "expence": "expense",
    "aprove": "approve",
    "aproved": "approved",
    "amunt": "amount",
    "paymnt": "payment",
    "projct": "project",
    "meralast": "mera last",
    "toal": "total",
    "kon": "kaun",
    "h": "hai",
    "mra": "mera"
}

def normalize_text(text):
    text = text.lower().strip()

    for bad, good in COMMON_FIXES.items():
        text = text.replace(bad, good)

    text = re.sub(r"\s+", " ", text)
    return text

# =========================
# MEMORY
# =========================
def save_employee_id(emp_id):
    memory_sheet.append_row([
        emp_id,
        "employee_id",
        emp_id,
        str(datetime.now())
    ])

def get_saved_employee_id():
    rows = memory_sheet.get_all_values()

    if len(rows) < 2:
        return None

    last_row = rows[-1]

    if len(last_row) >= 3:
        return last_row[2].strip().upper()

    return None

# =========================
# SHEET DATA
# =========================
def get_employee_rows(emp_id):
    all_rows = data_sheet.get_all_values()

    headers = []
    header_index = None

    for i, row in enumerate(all_rows):
        clean = [str(x).strip() for x in row]

        if "EMP ID" in clean and "Amount" in clean:
            headers = clean
            header_index = i
            break

    if header_index is None:
        return [], []

    data_rows = all_rows[header_index + 1:]
    emp_index = headers.index("EMP ID")

    matched = []

    for row in data_rows:
        while len(row) < len(headers):
            row.append("")

        value = str(row[emp_index]).strip().upper()

        if value == emp_id.upper():
            matched.append(row)

    return matched, headers

# =========================
# HELPERS
# =========================
def safe_idx(headers, col):
    return headers.index(col) if col in headers else None

def get_total(rows, headers, col):
    idx = safe_idx(headers, col)

    if idx is None:
        return 0

    total = 0

    for row in rows:
        try:
            total += float(str(row[idx]).replace(",", "").strip())
        except:
            pass

    return total

def latest_row(rows):
    return rows[-1] if rows else None

def get_name(rows, headers):
    idx = safe_idx(headers, "Name")
    return rows[0][idx] if idx is not None else "Name not found"

def get_project(rows, headers):
    idx = safe_idx(headers, "Project Name")
    return rows[0][idx] if idx is not None else "Project not found"

def get_last_expense(rows, headers):
    row = latest_row(rows)

    if not row:
        return None

    amt = safe_idx(headers, "Amount")
    desc = safe_idx(headers, "Description")

    return {
        "amount": row[amt] if amt is not None else "",
        "desc": row[desc] if desc is not None else ""
    }

def get_last_expense_date(rows, headers):
    row = latest_row(rows)

    if not row:
        return ""

    idx = safe_idx(headers, "Expense date")
    return row[idx] if idx is not None else ""
# =========================
# SMART SEARCH
# =========================
def get_expense_by_date(rows, headers, target_date):
    idx = safe_idx(headers, "Expense date")
    desc = safe_idx(headers, "Description")
    amt = safe_idx(headers, "Amount")

    if idx is None:
        return None

    for row in rows:
        val = row[idx].strip()

        if target_date in val:
            return {
                "desc": row[desc] if desc is not None else "",
                "amount": row[amt] if amt is not None else ""
            }

    return None


def get_pending_expenses(rows, headers):
    done = safe_idx(headers, "Done")
    desc = safe_idx(headers, "Description")

    data = []

    if done is None:
        return data

    for row in rows:
        val = row[done].strip().lower()

        if val not in ["approved", "done", "yes"]:
            data.append(row[desc])

    return data


def get_approved_but_unpaid(rows, headers):
    done = safe_idx(headers, "Done")
    paid = safe_idx(headers, "Paid Amount")
    desc = safe_idx(headers, "Description")

    data = []

    if done is None or paid is None:
        return data

    for row in rows:
        d = row[done].strip().lower()
        p = row[paid].strip()

        if d == "approved" and (p == "" or p == "0"):
            data.append(row[desc])

    return data


def get_expense_type(rows, headers, keyword):
    idx = safe_idx(headers, "Expense Type")
    desc = safe_idx(headers, "Description")

    result = []

    if idx is None:
        return result

    for row in rows:
        if keyword.lower() in row[idx].lower():
            result.append(row[desc])

    return result


# =========================
# GEMINI INTENT
# =========================
def parse_intent(user_text):
    prompt = f"""
User message: {user_text}

Return ONLY JSON.

Possible intents:
- name
- project
- total_expense
- paid_amount
- last_expense
- last_expense_date
- pending_expense
- approved_unpaid
- expense_by_date
- expense_type
- unknown

If date found, extract date.
If expense type found (hotel/travel/railway/etc), extract keyword.

Example:
{{"intent":"last_expense"}}
"""

    try:
        response = model.generate_content(prompt)
        txt = response.text.strip()

        match = re.search(r"\{.*\}", txt, re.S)
        if match:
            return json.loads(match.group())

    except:
        pass

       # MANUAL FALLBACK
    txt = user_text.lower()

    if "name" in txt:
        return {"intent": "name"}

    if "project" in txt:
        return {"intent": "project"}

    if "total" in txt and "expense" in txt:
        return {"intent": "total_expense"}

    if "paid" in txt and "amount" in txt:
        return {"intent": "paid_amount"}

    if "last expense date" in txt:
        return {"intent": "last_expense_date"}

    if "last expense" in txt:
        return {"intent": "last_expense"}

    if "approve nhi" in txt or "pending" in txt:
        return {"intent": "pending_expense"}

    if "approved" in txt and "paid nhi" in txt:
        return {"intent": "approved_unpaid"}

    return {"intent": "unknown"}


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/service-worker.js")
def sw():
    return send_from_directory(".", "service-worker.js")


@app.route("/chat", methods=["POST"])
def chat():
    user = request.json.get("message", "")
    text = normalize_text(user)

    # detect employee id
    match = re.search(r"E\d+", user.upper())
    if match:
        emp_id = match.group()
        save_employee_id(emp_id)

        return jsonify({
            "reply": f"Employee ID {emp_id} saved successfully."
        })

    emp_id = get_saved_employee_id()

    if not emp_id:
        return jsonify({
            "reply": "Pehle employee id batao. Example: meri employee id E033 hai."
        })

    rows, headers = get_employee_rows(emp_id)

    if not rows:
        return jsonify({
            "reply": f"Employee ID {emp_id} ka data nahi mila."
        })

    parsed = parse_intent(text)
    intent = parsed.get("intent", "unknown")

    # NAME
    if intent == "name":
        return jsonify({
            "reply": f"Aapka naam hai: {get_name(rows, headers)}"
        })

    # PROJECT
    if intent == "project":
        return jsonify({
            "reply": f"Aapka project hai: {get_project(rows, headers)}"
        })

    # TOTAL EXPENSE
    if intent == "total_expense":
        total = get_total(rows, headers, "Amount")
        return jsonify({
            "reply": f"Aapka total expense ₹{total}"
        })

    # PAID AMOUNT
    if intent == "paid_amount":
        total = get_total(rows, headers, "Paid Amount")
        return jsonify({
            "reply": f"Aapka total paid amount ₹{total}"
        })

    # LAST EXPENSE
    if intent == "last_expense":
        last = get_last_expense(rows, headers)

        return jsonify({
            "reply": f"Aapka last expense ₹{last['amount']} tha. Description: {last['desc']}"
        })

    # LAST EXPENSE DATE
    if intent == "last_expense_date":
        date = get_last_expense_date(rows, headers)

        return jsonify({
            "reply": f"Aapke last expense ki date {date} hai."
        })

    # PENDING
    if intent == "pending_expense":
        data = get_pending_expenses(rows, headers)

        return jsonify({
            "reply": "Pending expenses: " + ", ".join(data[:10]) if data else "Aapke sab expenses approved hain."
        })

    # APPROVED BUT UNPAID
    if intent == "approved_unpaid":
        data = get_approved_but_unpaid(rows, headers)

        return jsonify({
            "reply": "Approved but unpaid: " + ", ".join(data[:10]) if data else "Aisa koi expense nahi mila."
        })

    # DATE QUERY
    if intent == "expense_by_date":
        date = parsed.get("date", "")
        data = get_expense_by_date(rows, headers, date)

        if not data:
            return jsonify({
                "reply": "Us date ka expense nahi mila."
            })

        return jsonify({
            "reply": f"{date} ka expense: {data['desc']} ₹{data['amount']}"
        })

    # EXPENSE TYPE
    if intent == "expense_type":
        keyword = parsed.get("keyword", "")
        data = get_expense_type(rows, headers, keyword)

        return jsonify({
            "reply": f"{keyword} expenses: " + ", ".join(data[:10]) if data else f"{keyword} expense nahi mila."
        })

    # FALLBACK
    prompt = f"""
User asked: {user}

Employee ID: {emp_id}
Rows found: {len(rows)}

Answer in simple Hinglish.
If sheet me answer nahi ho:
"Mujhe iske bare me data nahi mila. PSH Admin se baat kare."
"""

    try:
        response = model.generate_content(prompt)

        return jsonify({
            "reply": response.text
        })

    except:
        return jsonify({
            "reply": "Mujhe iske bare me data nahi mila. PSH Admin se baat kare."
        })


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)