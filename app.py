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

st.set_page_config(page_title="Smart Expense Analyzer", page_icon="💸", layout="wide")

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

text = description.lower()

rules = {
        "Food": ["restaurant", "food", "grocery", "cafe", "coffee", "swiggy", "zomato"],
        "Travel": ["uber", "ola", "metro", "bus", "train", "flight", "fuel", "petrol"],
        "Shopping": ["amazon", "flipkart", "shopping", "mall", "clothing"],
        "Bills": ["electricity", "water", "internet", "mobile", "recharge", "rent"],
        "Entertainment": ["movie", "cinema", "netflix", "spotify", "concert"],
        "Healthcare": ["hospital", "pharmacy", "medical", "doctor", "clinic"],
        "Education": ["school", "college", "course", "tuition", "book"],
    }

for category, keywords in rules.items():
        if any(word in text for word in keywords):
            return category

return "Other"

def add_transaction(txn_date, description, amount, txn_type, category):
    description = description.strip()
    amount = round(float(amount), 2)

with connect_db() as connection:
        duplicate = connection.execute(
            """
            SELECT id FROM transactions
            WHERE txn_date = ?
              AND lower(description) = lower(?)
              AND amount = ?
              AND txn_type = ?
            LIMIT 1
            """,
            (txn_date, description, amount, txn_type),
        ).fetchone()

if duplicate:
            return False

connection.execute(
            """
            INSERT INTO transactions
                (txn_date, description, amount, txn_type, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            (txn_date, description, amount, txn_type, category),
        )

return True

def load_transactions():
    with connect_db() as connection:
        return pd.read_sql_query(
            """
            SELECT id, txn_date AS date, description, amount,
                   txn_type AS type, category
            FROM transactions
            ORDER BY txn_date DESC, id DESC
            """,
            connection,
        )

def parse_csv(uploaded_file):
    if uploaded_file.size > 5 * 1024 * 1024:
        return None, "File is too large. Maximum size is 5 MB."

data = pd.read_csv(uploaded_file, nrows=10001)


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
            data["description"].fillna("").astype(str).str.strip().str[:250]
        )
        data["amount"] = pd.to_numeric(data["amount"], errors="coerce").abs().round(2)

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

invalid_rows = int((~valid).sum())
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
                    if pd.notna(row["category"]) and str(row["category"]).strip()
                    else guess_category(row["description"], row["type"])
                ),
                axis=1,

