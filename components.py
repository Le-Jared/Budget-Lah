import os
import requests
import urllib.parse
import decimal
import sqlalchemy

from flask import redirect, render_template, request, session
from functools import wraps
from sqlalchemy.engine import Row

def apology(message, code=400):
    def escape(s):
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(old, new)
        return s
    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/blog")
        return f(*args, **kwargs)
    return decorated_function


def sgd(value):
    """Format value as SGD."""
    return f"SGD {value:,.2f}"


# Converts a list of SQL Alchemy RowProxy objects into a list of dictionary objects with the column name as the key (https://github.com/cs50/python-cs50/blob/develop/src/cs50/sql.py#L328)
# Used for SQL SELECT .fetchall() results
def convertSQLToDict(listOfRowProxy):
    # Coerce types
    rows = [row._asdict() for row in listOfRowProxy]
    for row in rows:
        for column in row:
            if type(row[column]) is decimal.Decimal:
                row[column] = float(row[column])
            # Coerce memoryview objects (as from PostgreSQL's bytea columns) to bytes
            elif type(row[column]) is memoryview:
                row[column] = bytes(row[column])

    return rows







