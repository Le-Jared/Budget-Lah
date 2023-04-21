import os

from flask import request, session
from flask_session import Session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import convertSQLToDict

# Create engine object to manage connections to DB, and scoped session to separate user interactions with DB
engine = create_engine(os.getenv("DATABASE_URL"),)
db = scoped_session(sessionmaker(bind=engine))


# Get the users account name
def getUsername(userID):
    result = db.execute(text(
        "SELECT username FROM users WHERE id = :usersID"), {"usersID": userID}).fetchone()

    if result is not None:
        return result[0]
    else:
        return None



# Get the users total income
def getIncome(userID):
    try:
        income = db.execute(text(
            "SELECT income FROM users WHERE id = :usersID"), {"usersID": userID}).fetchone()

        if not income or income[0] is None:
            return 0
        else:
            return float(income[0])
    except Exception as e:
        print("Error in getIncome:", e)
        return None



# Update the users income
def updateIncome(income, userID):
    rows = db.execute(text("UPDATE users SET income = :newIncome WHERE id = :usersID"),
                      {"newIncome": income, "usersID": userID}).rowcount
    db.commit()

    # Return an error message if the record could not be updated
    if rows != 1:
        return {"apology": "Sorry, Update Income is angry. Try again!"}
    else:
        return rows


# Get the users payers
def getPayers(userID):
    results = db.execute(text("SELECT name FROM payers WHERE user_id = :usersID ORDER BY name ASC"), {"usersID": userID}).fetchall()

    payers = convertSQLToDict(results)

    return payers


# Add a payer to the users account
def addPayer(name, userID):

    
    # the payers report charts have 5 hardcoded color pallettes that will need to be updated if the max number of payers is changed in the future)
    if getTotalPayers(userID) >= 5:
        return {"apology": "You have the maximum number of payers. Try deleting one you aren't using or contact the admin."}

    # Make sure the new payer does not already exist in the DB
    if payerExistsForUser(name, userID):
        return {"apology": "You already have a payer with that name. Enter a new, unique name."}
    else:
        # Insert new payer into DB
        row = db.execute(text("INSERT INTO payers (user_id, name) VALUES (:usersID, :name)"),
                         {"usersID": userID, "name": name}).rowcount
        db.commit()

        return row


# Rename a users existing payer
def renamePayer(existingName, newName, userID):
    # Make sure the existing name actually exists in the DB
    if not payerExistsForUser(existingName, userID):
        return {"apology": "The payer you're trying to rename does not exist."}

    # Make sure the new name does not already exist in the DB
    if payerExistsForUser(newName, userID):
        return {"apology": "You already have a payer with that name. Enter a new, unique name."}

    # Update existing *expense* records to usse the new name
    db.execute(text("UPDATE expenses SET payer = :name WHERE user_id = :usersID AND payer = :oldName"),
               {"name": newName, "usersID": userID, "oldName": existingName})
    db.commit()

    # Update the existing *payer* record with the new payers name
    rows = db.execute(text(
        "UPDATE payers SET name = :name WHERE user_id = :usersID AND name = :oldName"), {"name": newName, "usersID": userID, "oldName": existingName}).rowcount
    db.commit()

    # Return an error message if the record could not be updated
    if rows != 1:
        return {"apology": "Sorry, Rename Payer is having problems. Try again!"}
    else:
        return rows


# Delete a users existing payer
def deletePayer(name, userID):
    # Make sure the existing name actually exists in the DB
    if not payerExistsForUser(name, userID):
        return {"apology": "The payer you're trying to delete does not exist."}

    # Delete the record
    rows = db.execute(text("DELETE FROM payers WHERE name = :name AND user_id = :usersID"),
                      {"name": name, "usersID": userID}).rowcount
    db.commit()

    # Return an error message if the record could not be deleted
    if rows != 1:
        return {"apology": "Sorry, Delete payer isn't working for some reason. Try again!"}
    else:
        return rows


# Update the users password
def updatePassword(oldPass, newPass, userID):
    # Ensure the current password matches the hash in the DB
    userHash = db.execute(text(
        "SELECT hash FROM users WHERE id = :usersID"), {"usersID": userID}).fetchone()[0]
    if not check_password_hash(userHash, oldPass):
        return {"apology": "invalid password"}

    # Generate hash for new password
    hashedPass = generate_password_hash(newPass)

    # Update the users account to use the new password hash
    rows = db.execute(text("UPDATE users SET hash = :hashedPass WHERE id = :usersID"),
                      {"hashedPass": hashedPass, "usersID": userID}).rowcount
    db.commit()

    # Return an error message if the password could not be updated
    if rows != 1:
        return {"apology": "Sorry, Update Password is having issues. Try again!"}
    else:
        return rows


# Check to see if the payer name passed in exists in the DB or not
def payerExistsForUser(payerName, userID):
    # 'Self' always returns true / exists because it's the default payer name used for the user
    if payerName.lower() == 'self':
        return True

    # Query the DB
    count = db.execute(text("SELECT COUNT(*) AS count FROM payers WHERE user_id = :usersID AND LOWER(name) = :name"), {"usersID": userID, "name": payerName.lower()}).fetchone()[0]

    if count > 0:
        return True
    else:
        return False


# Get the users statistics
def getStatistics(userID):

    # Create a data structure to hold statistics
    stats = {"registerDate": None, "totalExpenses": None,
             "totalBudgets": None, "totalCategories": None, "totalPayers": None}

    # Get registration date
    result = db.execute(text("SELECT registerDate FROM users WHERE id = :usersID"), {"usersID": userID}).fetchone()
    if result is not None:
        registerDate = result[0]
        stats["registerDate"] = registerDate.split()[0]
    else:
        stats["registerDate"] = None

    # Get total expenses
    totalExpenses = db.execute(text(
        "SELECT COUNT(*) AS count FROM expenses WHERE user_id = :usersID"), {"usersID": userID}).fetchone()[0]
    stats["totalExpenses"] = totalExpenses

    # Get total budgets
    totalBudgets = db.execute(text(
        "SELECT COUNT(*) AS count FROM budgets WHERE user_id = :usersID"), {"usersID": userID}).fetchone()[0]
    stats["totalBudgets"] = totalBudgets

    # Get total categories
    totalCategories = db.execute(text(
        "SELECT COUNT(*) AS count FROM userCategories INNER JOIN categories ON userCategories.category_id = categories.id WHERE userCategories.user_id = :usersID"),
        {"usersID": userID}).fetchone()[0]
    stats["totalCategories"] = totalCategories

    # Get total payers
    totalPayers = getTotalPayers(userID)
    stats["totalPayers"] = totalPayers

    return stats


# Get a count of the total number of payers a user has
def getTotalPayers(userID):
    count = db.execute(text(
        "SELECT COUNT(*) AS count FROM payers WHERE user_id = :usersID"), {"usersID": userID}).fetchone()[0]

    return count


# Get all of the users account info for their 'Your Account' page
def getAllUserInfo(userID):

    # Create dict to hold user info
    user = {"name": None, "income": None, "payers": None, "stats": None}

    # Get the users account name
    user["name"] = getUsername(userID)

    # Get the users income
    user["income"] = getIncome(userID)

    # Get users payers
    user["payers"] = getPayers(userID)

    # Get the users stats
    user["stats"] = getStatistics(userID)

    return user
