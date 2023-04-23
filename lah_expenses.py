import os
import pandas as pd

from flask import request, session
from flask_session import Session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from datetime import datetime
from helpers import convertSQLToDict

# Create engine object to manage connections to DB, and scoped session to separate user interactions with DB
engine = create_engine(
    os.getenv("DATABASE_URL"),
    pool_size=20,
    max_overflow=0,
    pool_recycle=3600,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_use_lifo=True,
)
db = scoped_session(sessionmaker(bind=engine))


# Add expense(s) to the users expense records
# There are two entry points for this: 1) 'addexpenses' route and 2) 'index' route. #1 allows many expenses whereas #2 only allows 1 expense per POST.
def addExpenses(formData, userID):
    expenses = []
    expense = {"description": None, "category": None,
               "date": None, "amount": None, "payer": None}

    # Check if the user is submitting via 'addexpenses' or 'index' route - this determines if a user is adding 1 or potentially many expenses in a single POST
    if "." not in formData[0][0]:
        for key, value in formData:
            # Add to dictionary
            expense[key] = value.strip()

        # Convert the amount from string to float for the DB
        expense["amount"] = float(expense["amount"])

        # Add dictionary to list (to comply with design/standard of expensed.html)
        expenses.append(expense)

    # User is submitting via 'addexpenses' route
    else:
        counter = 0
        for key, value in formData:
            # Keys are numbered by default in HTML form. Remove those numbers so we can use the HTML element names as keys for the dictionary.
            cleanKey = key.split(".")

            # Add to dictionary
            expense[cleanKey[0]] = value.strip()

            # Every 5 loops add the expense to the list of expenses (because there are 5 fields for an expense record)
            counter += 1
            if counter % 5 == 0:
                # Store the amount as a float
                expense["amount"] = float(expense["amount"])

                # Add dictionary to list
                expenses.append(expense.copy())

    # Insert expenses into DB using the new addExpensesList function
    addExpensesList(expenses, userID)

    return expenses



# Get and return the users lifetime expense history
def getHistory(userID):
    results = db.execute(text("SELECT description, category, expenseDate AS date, payer, amount, submitTime FROM expenses WHERE user_id = :usersID ORDER BY id ASC"),
                         {"usersID": userID}).fetchall()

    history = convertSQLToDict(results)

    return history


# Get and return an existing expense record with ID from the DB
def getExpense(formData, userID):
    expense = {"description": None, "category": None,
               "date": None, "amount": None, "payer": None, "submitTime": None, "id": None}
    expense["description"] = formData.get("oldDescription").strip()
    expense["category"] = formData.get("oldCategory").strip()
    expense["date"] = formData.get("oldDate").strip()
    expense["amount"] = formData.get("oldAmount").strip()
    expense["payer"] = formData.get("oldPayer").strip()
    expense["submitTime"] = formData.get("submitTime").strip()

    # Remove dollar sign and comma from the old expense so we can convert to float for the DB
    expense["amount"] = float(
        expense["amount"].replace("$", "").replace(",", ""))

    # Query the DB for the expense unique identifier
    expenseID = db.execute(text("SELECT id FROM expenses WHERE user_id = :usersID AND description = :oldDescription AND category = :oldCategory AND expenseDate = :oldDate AND amount = :oldAmount AND payer = :oldPayer"),
                       {"usersID": userID, "oldDescription": expense["description"], "oldCategory": expense["category"], "oldDate": expense["date"], "oldAmount": expense["amount"], "oldPayer": expense["payer"]}).fetchone()


    # Make sure a record was found for the expense otherwise set as None
    if expenseID:
        expense["id"] = expenseID[0]
    else:
        expense["id"] = None

    return expense



# Delete an existing expense record for the user
def deleteExpense(expense, userID):
    result = db.execute(text("DELETE FROM expenses WHERE user_id = :usersID AND id = :oldExpenseID"),
                        {"usersID": userID, "oldExpenseID": expense["id"]})
    db.commit()

    return result


# Update an existing expense record for the user
def updateExpense(oldExpense, formData, userID):
    expense = {"description": None, "category": None,
               "date": None, "amount": None, "payer": None}
    expense["description"] = formData.get("description").strip()
    expense["category"] = formData.get("category").strip()
    expense["date"] = formData.get("date").strip()
    expense["amount"] = formData.get("amount").strip()
    expense["payer"] = formData.get("payer").strip()

    # Convert the amount from string to float for the DB
    expense["amount"] = float(expense["amount"])

    # Make sure the user actually is submitting changes and not saving the existing expense again
    hasChanges = False
    for key, value in oldExpense.items():
        # Exit the loop when reaching submitTime since that is not something the user provides in the form for a new expense
        if key == "submitTime":
            break
        else:
            if oldExpense[key] != expense[key]:
                hasChanges = True
                break
    if hasChanges is False:
        return None

    # Update the existing record
    now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    result = db.execute(text("UPDATE expenses SET description = :newDescription, category = :newCategory, expenseDate = :newDate, amount = :newAmount, payer = :newPayer, submitTime = :newSubmitTime WHERE id = :existingExpenseID AND user_id = :usersID"),
                        {"newDescription": expense["description"], "newCategory": expense["category"], "newDate": expense["date"], "newAmount": expense["amount"], "newPayer": expense["payer"], "newSubmitTime": now, "existingExpenseID": oldExpense["id"], "usersID": userID}).rowcount
    db.commit()

    # Make sure result is not empty (indicating it could not update the expense)
    if result:
        # Add dictionary to list (to comply with design/standard of expensed.html)
        expenses = []
        expenses.append(expense)
        return expenses
    else:
        return None



def addExpensesList(expenses, userID, return_ids=False):
    expense_ids = []
    count = 0
    
    # Insert expenses into DB
    for expense in expenses:
        now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        result = db.execute(text("INSERT INTO expenses (description, category, expenseDate, amount, payer, submitTime, user_id) VALUES (:description, :category, :expenseDate, :amount, :payer, :submitTime, :usersID) RETURNING id"),
                            {"description": expense["description"], "category": expense["category"], "expenseDate": expense["date"], "amount": expense["amount"], "payer": expense["payer"], "submitTime": now, "usersID": userID})
        expense_id = result.fetchone()[0]
        expense_ids.append(expense_id)
        count += 1

    db.commit()
    
    return expense_ids


def importExpensesFromFile(file, userID):
    expenses = []

    # Read the file (CSV or XLS) into a DataFrame
    file_extension = file.split('.')[-1].lower()
    if file_extension == 'xls':
        df = pd.read_excel(file, engine='xlrd', skiprows=9, header=None)
    elif file_extension == 'xlsx':
        df = pd.read_excel(file, engine='openpyxl', skiprows=9, header=None)
    else:
        raise ValueError(f"Unsupported file format: {file_extension}")

    # Get the current time to use as submitTime for all imported expenses
    now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

    # Iterate over the DataFrame rows and create the expenses list
    for index, row in df.iterrows():
        if index == 0:
            continue

        # Check if the row is blank (all elements are NaN) and break the loop if it is
        if row.isna().all():
            break

        if not pd.isna(row[0]):  # Check if the row has a transaction date (skip summary rows)
            description = row[2].split("SINGAPORE")[0].strip()

            expense = {"description": description,
                       "category": "Other",
                       "date": datetime.strptime(row[0], "%d %b %Y").strftime("%Y-%m-%d"),  # Convert date to string format
                       "amount": float(row[6]),
                       "payer": "Self"}

            expenses.append(expense)

    # Use the existing addExpensesList function to add the expenses to the database
    expense_ids = addExpensesList(expenses, userID)

    return expense_ids







