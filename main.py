import re
from datetime import datetime
import gspread
import google.generativeai as genai
from google.oauth2.service_account import Credentials

# =========================
# GEMINI SETUP
# =========================
genai.configure(api_key="AIzaSyB3yGnqmtiRMT3OPb6Aeu7vAWqcxR55X0c")
model = genai.GenerativeModel("gemini-2.5-flash")

# =========================
# GOOGLE SHEETS SETUP
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
    return rows[-1][2].strip().upper()


# =========================
# DATA
# =========================
def get_employee_rows(emp_id):
    all_rows = data_sheet.get_all_values()

    headers = []
    header_index = None

    # find header row dynamically
    for i, row in enumerate(all_rows):
        clean = [str(x).strip() for x in row]
        if "EMP ID" in clean and "Amount" in clean:
            headers = clean
            header_index = i
            break

    if header_index is None:
        print("DEBUG: Header row not found")
        return [], []

    print("DEBUG HEADERS:", headers)

    data_rows = all_rows[header_index + 1:]
    emp_index = headers.index("EMP ID")

    matched = []

    for row in data_rows:
        while len(row) < len(headers):
            row.append("")

        value = str(row[emp_index]).strip().upper()

        if value == emp_id.upper():
            matched.append(row)

    print("DEBUG MATCHED:", len(matched))
    return matched, headers


def get_total_expense(rows, headers):
    amount_index = headers.index("Amount")
    total = 0

    for row in rows:
        try:
            total += float(row[amount_index])
        except:
            pass

    return total


def get_last_expense(rows, headers):
    amount_index = headers.index("Amount")
    desc_index = headers.index("Description")

    last = rows[-1]

    return {
        "amount": last[amount_index],
        "desc": last[desc_index]
    }


def get_project(rows, headers):
    project_index = headers.index("Project Name")
    return rows[0][project_index]


def get_name(rows, headers):
    name_index = headers.index("Name")
    return rows[0][name_index]


# =========================
# CHATBOT
# =========================
print("AI Expense Assistant Started 🚀")
print("Type 'exit' to stop.\n")

while True:
    user = input("You: ")

    if user.lower() == "exit":
        break

    text = user.lower()

    # detect employee id
    match = re.search(r"E\d+", user.upper())
    if match:
        emp_id = match.group()
        save_employee_id(emp_id)
        print(f"Bot: Employee ID {emp_id} saved successfully.")
        continue

    emp_id = get_saved_employee_id()

    if not emp_id:
        print("Bot: Pehle employee id batao. Example: meri employee id E033 hai.")
        continue

    rows, headers = get_employee_rows(emp_id)

    if not rows:
        print(f"Bot: Employee ID {emp_id} ka data nahi mila.")
        continue

    # total expense
    if "total expense" in text or "overall expense" in text:
        total = get_total_expense(rows, headers)
        print(f"Bot: Aapka total expense ₹{total}")
        continue

    # last expense
    if "last expense" in text:
        last = get_last_expense(rows, headers)
        print(f"Bot: Aapka last expense ₹{last['amount']} tha. Description: {last['desc']}")
        continue

    # project
    if "project" in text:
        project = get_project(rows, headers)
        print(f"Bot: Aapka project hai: {project}")
        continue

    # name
    if "name" in text:
        name = get_name(rows, headers)
        print(f"Bot: Aapka naam hai: {name}")
        continue

    # fallback
    prompt = f"""
User asked: {user}
Reply in simple Hinglish only.
If answer not found in expense sheet, say:
'Mujhe iske bare me data nahi mila. PSH Admin se baat kare.'
"""

    try:
        response = model.generate_content(prompt)
        print("Bot:", response.text)
    except:
        print("Bot: Mujhe iske bare me data nahi mila. PSH Admin se baat kare.")