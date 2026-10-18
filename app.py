import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).with_name("expenses.db")

CATEGORIES = [
    "Food",
    "Travel",
    "Shopping",
    "Bills",
    "Entertainment",
    "Healthcare",
    "Education",
    "Other",
]

st.set_page_config(
    page_title="Smart Expense Analyzer",
    page_icon="💸",
    layout="wide",
)

def connect_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def initialize_database():
    with connect_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txn_date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                txn_type TEXT NOT NULL CHECK(txn_type IN ('Expense', 'Income')),
                category TEXT NOT NULL
            )
            """
        )

def guess_category(description, txn_type):
    if txn_type == "Income":
        return "Income"

text = str(description).lower()

rules = {
        "Food": [
            "restaurant", "food", "grocery", "cafe", "coffee",
            "swiggy", "zomato",
        ],
        "Travel": [
            "uber", "ola", "metro", "bus", "train", "flight",
            "fuel", "petrol",
        ],
        "Shopping": [
            "amazon", "flipkart", "shopping", "mall", "clothing",
        ],
        "Bills": [
            "electricity", "water", "internet", "mobile",
            "recharge", "rent",
        ],
        "Entertainment": [
            "movie", "cinema", "netflix", "spotify", "concert",
        ],
        "Healthcare": [
            "hospital", "pharmacy", "medical", "doctor", "clinic",
        ],
        "Education": [
            "school", "college", "course", "tuition", "book",
        ],
    }

for category, keywords in rules.items():
        if any(word in text for word in keywords):
            return category

return "Other"

def add_transaction(txn_date, description, amount, txn_type, category):
    description = str(description).strip()

try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        return False

if not description or amount <= 0:
        return False

if txn_type == "Income":
        category = "Income"

with connect_db() as connection:
        duplicate = connection.execute(
            """
            SELECT id
            FROM transactions
            WHERE txn_date = ?
              AND lower(description) = lower(?)
              AND amount = ?
              AND txn_type = ?
            LIMIT 1
            """,
            (str(txn_date), description, amount, txn_type),
        ).fetchone()

if duplicate:
            return False

connection.execute(
            """
            INSERT INTO transactions
                (txn_date, description, amount, txn_type, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(txn_date), description, amount, txn_type, category),
        )

return True

def load_transactions():
    with connect_db() as connection:
        return pd.read_sql_query(
            """
            SELECT id,
                   txn_date AS date,
                   description,
                   amount,
                   txn_type AS type,
                   category
            FROM transactions
            ORDER BY txn_date DESC, id DESC
            """,
            connection,
        )

def parse_csv(uploaded_file):
    """Read and validate an uploaded transaction CSV."""
    if uploaded_file.size > 5 * 1024 * 1024:
        return None, "File is too large. Maximum size is 5 MB."

try:
        data = pd.read_csv(uploaded_file, nrows=10001)
    except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
        return None, "Could not read the CSV. Check that it is a valid CSV file."

if len(data) > 10000:
        return None, "The CSV has more than 10,000 rows. Please split it."

data.columns = [str(column).strip().lower() for column in data.columns]

required = {"date", "description", "amount"}
    if not required.issubset(data.columns):
        return None, "CSV needs columns: date, description, amount."

data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    data["description"] = (
        data["description"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str[:250]
    )
    data["amount"] = (
        pd.to_numeric(data["amount"], errors="coerce")
        .abs()
        .round(2)
    )

if "type" in data.columns:
        type_map = {
            "expense": "Expense",
            "debit": "Expense",
            "income": "Income",
            "credit": "Income",
        }
        data["type"] = (
            data["type"]
            .fillna("Expense")
            .astype(str)
            .str.strip()
            .str.lower()
            .map(type_map)
        )
    else:
        data["type"] = "Expense"

valid = (
        data["date"].notna()
        & data["description"].ne("")
        & data["amount"].notna()
        & data["amount"].gt(0)
        & data["type"].notna()
    )

data = data.loc[valid].copy()

if data.empty:
        return None, "No valid transactions found in the CSV."

if "category" not in data.columns:
        data["category"] = [
            guess_category(description, txn_type)
            for description, txn_type in zip(data["description"], data["type"])
        ]
    else:
        data["category"] = data.apply(
            lambda row: (
                str(row["category"]).strip()[:60]
                if pd.notna(row["category"])
                and str(row["category"]).strip()
                else guess_category(row["description"], row["type"])
            ),
            axis=1,
        )

data.loc[data["type"] == "Income", "category"] = "Income"

return data[["date", "description", "amount", "type", "category"]], None

def format_inr(value):
    return f"₹{value:,.2f}"

initialize_database()

st.title("💸 Smart Expense Analyzer")
st.caption("Record transactions, import a CSV, and review your spending.")

with st.sidebar:
    st.header("Add a transaction")

with st.form("add_transaction_form", clear_on_submit=True):
        transaction_date = st.date_input("Date", value=date.today())
        description = st.text_input("Description")
        amount = st.number_input(
            "Amount (₹)",
            min_value=0.01,
            value=100.00,
            step=50.00,
        )
        transaction_type = st.selectbox("Type", ["Expense", "Income"])

category_choice = st.selectbox(
            "Category",
            ["Auto-detect"] + CATEGORIES,
            disabled=transaction_type == "Income",
        )

submitted = st.form_submit_button("Add transaction")

if submitted:
        if not description.strip():
            st.error("Please enter a description.")
        else:
            category = (
                "Income"
                if transaction_type == "Income"
                else (
                    guess_category(description, transaction_type)
                    if category_choice == "Auto-detect"
                    else category_choice
                )
            )

added = add_transaction(
                transaction_date.isoformat(),
                description,
                amount,
                transaction_type,
                category,
            )

if added:
                st.success("Transaction added.")
                st.rerun()
            else:
                st.warning("That transaction already exists or has invalid details.")

st.divider()
    st.header("Import a CSV")
    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])

if uploaded_file is not None:
        csv_data, csv_error = parse_csv(uploaded_file)

if csv_error:
            st.error(csv_error)
        else:
            st.write(f"Valid transactions found: **{len(csv_data)}**")
            st.dataframe(csv_data.head(10), use_container_width=True)

if st.button("Import transactions"):
                imported = 0
                skipped = 0

for row in csv_data.itertuples(index=False):
                    if add_transaction(
                        row.date,
                        row.description,
                        row.amount,
                        row.type,
                        row.category,
                    ):
                        imported += 1
                    else:
                        skipped += 1

st.success(
                    f"Imported {imported} transaction(s); "
                    f"skipped {skipped} duplicate or invalid row(s)."
                )
                st.rerun()

transactions = load_transactions()

if transactions.empty:
    st.info("No transactions yet. Add one in the sidebar or import a CSV.")
    st.stop()

transactions["date"] = pd.to_datetime(transactions["date"], errors="coerce")
transactions = transactions.dropna(subset=["date"])
transactions["amount"] = pd.to_numeric(
    transactions["amount"], errors="coerce"
).fillna(0)

today = date.today()
this_month = transactions[
    (transactions["date"].dt.year == today.year)
    & (transactions["date"].dt.month == today.month)
]

monthly_expenses = this_month.loc[
    this_month["type"] == "Expense", "amount"
].sum()
monthly_income = this_month.loc[
    this_month["type"] == "Income", "amount"
].sum()
all_expenses = transactions.loc[
    transactions["type"] == "Expense", "amount"
].sum()

st.subheader("Overview")

col1, col2, col3 = st.columns(3)
col1.metric("Expenses this month", format_inr(monthly_expenses))
col2.metric("Income this month", format_inr(monthly_income))
col3.metric("All-time expenses", format_inr(all_expenses))

with st.expander("Monthly budget"):
    monthly_budget = st.number_input(
        "Set a monthly expense budget (₹)",
        min_value=0.0,
        value=0.0,
        step=500.0,
    )

if monthly_budget > 0:
        remaining = monthly_budget - monthly_expenses
        if remaining >= 0:
            st.success(f"Remaining this month: {format_inr(remaining)}")
        else:
            st.warning(f"Over budget by: {format_inr(abs(remaining))}")

st.subheader("This month's expenses by category")

monthly_expense_rows = this_month[this_month["type"] == "Expense"]

if monthly_expense_rows.empty:
    st.info("There are no expenses recorded for this month.")
else:
    category_totals = (
        monthly_expense_rows.groupby("category")["amount"]
        .sum()
        .sort_values(ascending=False)
    )
    st.bar_chart(category_totals)

st.subheader("Daily expenses this month")

if monthly_expense_rows.empty:
    st.info("No daily expense data to show yet.")
else:
    daily_totals = (
        monthly_expense_rows.assign(
            day=monthly_expense_rows["date"].dt.strftime("%Y-%m-%d")
        )
        .groupby("day")["amount"]
        .sum()
        .sort_index()
    )
    st.line_chart(daily_totals)

st.subheader("Transactions")
display_transactions = transactions.copy()
display_transactions["date"] = display_transactions["date"].dt.strftime("%Y-%m-%d")
display_transactions["amount"] = display_transactions["amount"].map(format_inr)

st.dataframe(
    display_transactions[
        ["date", "description", "type", "category", "amount"]
    ],
    use_container_width=True,
    hide_index=True,
)
