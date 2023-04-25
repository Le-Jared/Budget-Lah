import os
import pathlib
import lah_dashboard
import lah_expenses
import lah_budgets
import lah_categories
import lah_reports
import lah_account
import requests 

from flask import Flask, redirect, render_template, request, session, url_for, flash, abort
from flask_session import Session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from flask_wtf.csrf import CSRFProtect
from pip._vendor import cachecontrol
from components import apology, login_required, sgd
from google.oauth2 import id_token
from pip._vendor import cachecontrol
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests


# Configure application
app = Flask(__name__)

# Set app key
app.secret_key = os.getenv("SECRET_KEY")

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Configure session to use filesystem (instead of signed cookies)
# app.config["SESSION_FILE_DIR"] = mkdtemp() # only remove comment when testing locally for benefit of temp directories
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Custom filter
app.jinja_env.filters["sgd"] = sgd

# Enable CSRF protection globally for the Flask app
csrf = CSRFProtect(app)

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

# Set up the Google OAuth2 client
GOOGLE_CLIENT_ID = "495675858702-3nnj7rb14ba2c4nru81b8e7ttuqce1h7.apps.googleusercontent.com"
client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")

flow = Flow.from_client_secrets_file(
    client_secrets_file=client_secrets_file,
    scopes=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
    redirect_uri="http://127.0.0.1:5000/callback"
)

@app.route("/google-login")
def google_login():
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    flow.fetch_token(authorization_response=request.url)

    if not session["state"] == request.args["state"]:
        abort(500)  # State does not match!

    credentials = flow.credentials
    request_session = requests.session()
    cached_session = cachecontrol.CacheControl(request_session)
    token_request = google.auth.transport.requests.Request(session=cached_session)

    id_info = id_token.verify_oauth2_token(
        id_token=credentials._id_token,
        request=token_request,
        audience=GOOGLE_CLIENT_ID
    )

    user_id = id_info.get("sub")
    user_email = id_info.get("email")
    user_name = id_info.get("name")

    # Check if the user exists in your database, if not, create a new user
    result = db.execute(text("SELECT * FROM users WHERE google_id = :google_id"),
                        {"google_id": user_id})
    column_names = result.keys()
    rows = [dict(zip(column_names, row)) for row in result.fetchall()]


    if len(rows) == 0:
        # Generate a unique username based on the user's email address
        username_base = user_email.split('@')[0]
        username = username_base
        username_count = 1

        while True:
            existing_user = db.execute(text("SELECT * FROM users WHERE LOWER(username) = :username"), {"username": username.lower()}).fetchone()
            if not existing_user:
                break
            username = f"{username_base}_{username_count}"
            username_count += 1

        # Create a new user in your database with the Google user information
        now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        new_user_id = db.execute(text("INSERT INTO users (username, email, google_id, registerDate, lastLogin) VALUES (:username, :email, :google_id, :registerDate, :lastLogin) RETURNING id"),
                                 {"username": username, "email": user_email, "google_id": user_id, "registerDate": now, "lastLogin": now}).fetchone()[0]
        db.commit()

        session["user_id"] = new_user_id
    else:
        session["user_id"] = rows[0]['id']

    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
    # User reached route via POST
    if request.method == "POST":
        # Query DB for all existing user names and make sure new username isn't already taken
        username = request.form.get("username").strip()
        existingUsers = db.execute(text("SELECT username FROM users WHERE LOWER(username) = :username"), {"username": username.lower()}).fetchone()
        if existingUsers:
            return render_template("register.html", username=username)

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 403)

        # Ensure password was submitted
        password = request.form.get("password")
        if not password:
            return apology("must provide password", 403)

        # Insert user into the database
        hashedPass = generate_password_hash(password)
        now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        newUserID = db.execute(text("INSERT INTO users (username, hash, registerDate, lastLogin) VALUES (:username, :hashedPass, :registerDate, :lastLogin) RETURNING id"),
                               {"username": username, "hashedPass": hashedPass, "registerDate": now, "lastLogin": now}).fetchone()[0]
        db.commit()

        # Create default spending categories for user
        db.execute(text("INSERT INTO userCategories (category_id, user_id) VALUES (1, :usersID), (2, :usersID), (3, :usersID), (4, :usersID), (5, :usersID), (6, :usersID), (7, :usersID), (8, :usersID)"),
           {"usersID": newUserID})

        db.commit()

        # Auto-login the user after creating their username
        session["user_id"] = newUserID

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET
    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    # Forget any user_id
    session.clear()

    # User reached route via POST
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        result = db.execute(text("SELECT * FROM users WHERE username = :username"),
                            {"username": request.form.get("username")})
        rows = result.fetchall()

        # Get the index of 'hash' and 'id' columns
        hash_index = list(result.keys()).index("hash")
        id_index = list(result.keys()).index("id")

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0][hash_index], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0][id_index]

        # Record the login time
        now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        db.execute(text("UPDATE users SET lastLogin = :lastLogin WHERE id = :usersID"),
                   {"lastLogin": now, "usersID": session["user_id"]})
        db.commit()

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    # User reached route via GET
    if request.method == "GET":

        # Initialize metrics to None to render the appropriate UX if data does not exist yet for the user
        expenses_year = None
        expenses_month = None
        expenses_week = None
        expenses_last5 = None
        spending_week = []
        spending_month = []

        # Get the users spend categories (for quick expense modal)
        categories = lah_categories.getSpendCategories(session["user_id"])

        # Get the users payers (for quick expense modal)
        payers = lah_account.getPayers(session["user_id"])

        # Get todays date (for quick expense modal)
        date = datetime.today().strftime('%Y-%m-%d')

        # Get the users income
        income = lah_account.getIncome(session["user_id"])

        # Get current years total expenses for the user
        expenses_year = lah_dashboard.getTotalSpend_Year(session["user_id"])
        print("expenses_year:", expenses_year)

        # Get current months total expenses for the user
        expenses_month = lah_dashboard.getTotalSpend_Month(session["user_id"])
        print("expenses_month:", expenses_month)

        # Get current week total expenses for the user
        expenses_week = lah_dashboard.getTotalSpend_Week(session["user_id"])

        # Get last 5 expenses for the user
        expenses_last5 = lah_dashboard.getLastFiveExpenses(session["user_id"])

        # Get every budgets spent/remaining for the user
        budgets = lah_dashboard.getBudgets(session["user_id"])

        # Get weekly spending for the user
        weeks = lah_dashboard.getLastFourWeekNames()
        spending_week = lah_dashboard.getWeeklySpending(
            weeks, session["user_id"])

        # Get monthly spending for the user (for the current year)
        spending_month = lah_dashboard.getMonthlySpending(
            session["user_id"])

        # Get spending trends for the user
        spending_trends = lah_dashboard.getSpendingTrends(
            session["user_id"])

        # Get payer spending for the user
        payersChart = lah_reports.generatePayersReport(session["user_id"])

        return render_template("index.html", categories=categories, payers=payers, date=date, income=income, expenses_year=expenses_year, expenses_month=expenses_month, expenses_week=expenses_week, expenses_last5=expenses_last5,
                               budgets=budgets, spending_week=spending_week, spending_month=spending_month, spending_trends=spending_trends, payersChart=payersChart)

    # User reached route via POST
    else:
        # Get all of the expenses provided from the HTML form
        formData = list(request.form.items())

        # Remove CSRF field from form data before processing
        formData.pop(0)

        # Add expenses to the DB for user
        expenses = lah_expenses.addExpenses(formData, session["user_id"])

        # Redirect to results page and render a summary of the submitted expenses
        return render_template("expensed.html", results=expenses)


@app.route("/expenses", methods=["GET"])
@login_required
def expenses():
    return render_template("expenses.html")


@app.route("/addexpenses", methods=["GET", "POST"])
@login_required
def addexpenses():
    # User reached route via POST
    if request.method == "POST":
        # Get all of the expenses provided from the HTML form
        formData = list(request.form.items())

        # Remove CSRF field from form data before processing
        formData.pop(0)

        # Add expenses to the DB for user
        expenses = lah_expenses.addExpenses(formData, session["user_id"])

        # Redirect to results page and render a summary of the submitted expenses
        return render_template("expensed.html", results=expenses)

    # User reached route via GET
    else:
        # Get the users spend categories
        categories = lah_categories.getSpendCategories(session["user_id"])

        # Get the users payers
        payers = lah_account.getPayers(session["user_id"])

        # Render expense page
        date = datetime.today().strftime('%Y-%m-%d')

        return render_template("addexpenses.html", categories=categories, date=date, payers=payers)


@app.route("/expensehistory", methods=["GET", "POST"])
@login_required
def expensehistory():
    # User reached route via GET
    if request.method == "GET":
        # Get all of the users expense history ordered by submission time
        history = lah_expenses.getHistory(session["user_id"])

        # Get the users spend categories
        categories = lah_categories.getSpendCategories(session["user_id"])

        # Get the users payers (for modal)
        payers = lah_account.getPayers(session["user_id"])

        return render_template("expensehistory.html", history=history, categories=categories, payers=payers, isDeleteAlert=False)

    # User reached route via POST
    else:
        # Initialize users action
        userHasSelected_deleteExpense = False

        # Determine what action was selected by the user (button/form trick from: https://stackoverflow.com/questions/26217779/how-to-get-the-name-of-a-submitted-form-in-flask)
        if "btnDeleteConfirm" in request.form:
            userHasSelected_deleteExpense = True
        elif "btnSave" in request.form:
            userHasSelected_deleteExpense = False
        else:
            return apology("Try again!")

        # Get the existing expense record ID from the DB and build a data structure to store old expense details
        oldExpense = lah_expenses.getExpense(request.form, session["user_id"])

        # Make sure an existing record was found otherwise render an error message
        if oldExpense["id"] == None:
            return apology("The expense record you're trying to update doesn't exist")

        # Delete the existing expense record
        if userHasSelected_deleteExpense == True:

            # Delete the old record from the DB
            deleted = lah_expenses.deleteExpense(
                oldExpense, session["user_id"])
            if not deleted:
                return apology("The expense was unable to be deleted")

            # Get the users expense history, spend categories, payers, and then render the history page w/ delete alert
            history = lah_expenses.getHistory(session["user_id"])
            categories = lah_categories.getSpendCategories(
                session["user_id"])
            payers = lah_account.getPayers(session["user_id"])
            return render_template("expensehistory.html", history=history, categories=categories, payers=payers, isDeleteAlert=True)

        # Update the existing expense record
        else:
            # Update the old record with new details from the form
            expensed = lah_expenses.updateExpense(
                oldExpense, request.form, session["user_id"])
            if not expensed:
                return apology("The expense was unable to be updated")

            # Redirect to results page and render a summary of the updated expense
            return render_template("expensed.html", results=expensed)


@app.route("/budgets", methods=["GET", "POST"])
@app.route("/budgets/<int:year>", methods=["GET"])
@login_required
def budgets(year=None):
    # Make sure the year from route is valid
    if year:
        currentYear = datetime.now().year
        if not 2023 <= year <= currentYear:
            return apology(f"Please select a valid budget year: 2023 through {currentYear}")
    else:
        # Set year to current year if it was not in the route (this will set UX to display current years budgets)
        year = datetime.now().year

    # User reached route via GET
    if request.method == "GET":
        # Get the users income
        income = lah_account.getIncome(session["user_id"])

        # Get the users current budgets
        budgets = lah_budgets.getBudgets(session["user_id"])

        # Get the users total budgeted amount
        budgeted = lah_budgets.getTotalBudgetedByYear(
            session["user_id"], year)

        return render_template("budgets.html", income=income, budgets=budgets, year=year, budgeted=budgeted, deletedBudgetName=None)

    # User reached route via POST
    else:
        # Get the name of the budget the user wants to delete
        budgetName = request.form.get("delete").strip()

        # Delete the budget
        deletedBudgetName = lah_budgets.deleteBudget(
            budgetName, session["user_id"])

        # Render the budgets page with a success message, otherwise throw an error/apology
        if deletedBudgetName:
            # Get the users income, current budgets, and sum their budgeted amount unless they don't have any budgets (same steps as a GET for this route)
            income = lah_account.getIncome(session["user_id"])
            budgets = lah_budgets.getBudgets(session["user_id"])
            budgeted = lah_budgets.getTotalBudgetedByYear(
                session["user_id"], year)

            return render_template("budgets.html", income=income, budgets=budgets, year=year, budgeted=budgeted, deletedBudgetName=deletedBudgetName)
        else:
            return apology("Uh oh! Your budget could not be deleted.")


@app.route("/createbudget", methods=["GET", "POST"])
@login_required
def createbudget():
    # User reached route via POST
    if request.method == "POST":
        # Make sure user has no more than 20 budgets (note: 20 is an arbitrary value)
        budgets = lah_budgets.getBudgets(session["user_id"])
        if budgets:
            budgetCount = 0
            for year in budgets:
                budgetCount += len(budgets[year])
            if budgetCount >= 20:
                return apology("You've reached the max amount of budgets'")

        # Get all of the budget info provided from the HTML form
        formData = list(request.form.items())

        # Remove CSRF field from form data before processing
        formData.pop(0)

        # Generate data structure to hold budget info from form
        budgetDict = lah_budgets.generateBudgetFromForm(formData)

        # Render error message if budget name or categories contained invalid data
        if "apology" in budgetDict:
            return apology(budgetDict["apology"])
        else:
            # Add budget to DB for user
            budget = lah_budgets.createBudget(
                budgetDict, session["user_id"])
            # Render error message if budget name is a duplicate of another budget the user has
            if "apology" in budget:
                return apology(budget["apology"])
            else:
                return render_template("budgetcreated.html", results=budget)
    else:
        # Get the users income
        income = lah_account.getIncome(session["user_id"])

        # Get the users total budgeted amount
        budgeted = lah_budgets.getTotalBudgetedByYear(session["user_id"])

        # Get the users spend categories
        categories = lah_categories.getSpendCategories(session["user_id"])

        return render_template("createbudget.html", income=income, budgeted=budgeted, categories=categories)


@app.route("/updatebudget/<urlvar_budgetname>", methods=["GET", "POST"])
@login_required
def updatebudget(urlvar_budgetname):
    # User reached route via POST
    if request.method == "POST":
        # Get all of the budget info provided from the HTML form
        formData = list(request.form.items())

        # Remove CSRF field from form data before processing
        formData.pop(0)

        # Generate data structure to hold budget info from form
        budgetDict = lah_budgets.generateBudgetFromForm(formData)

        # Render error message if budget name or categories contained invalid data
        if "apology" in budgetDict:
            return apology(budgetDict["apology"])
        else:
            # Update budget in the DB for user
            budget = lah_budgets.updateBudget(
                urlvar_budgetname, budgetDict, session["user_id"])

            # Render error message if budget name is a duplicate of another budget the user has
            if "apology" in budget:
                return apology(budget["apology"])
            else:
                return render_template("budgetcreated.html", results=budget)

    # User reached route via GET
    else:
        # Get the budget details from the DB based on the budget name provided via URL. Throw an apology/error if budget can't be found.
        budgetID = lah_budgets.getBudgetID(
            urlvar_budgetname, session["user_id"])
        if budgetID is None:
            return apology("'" + urlvar_budgetname + "' budget does not exist")
        else:
            budget = lah_budgets.getBudgetByID(budgetID, session["user_id"])

        # Get the users income
        income = lah_account.getIncome(session["user_id"])

        # Get the users total budgeted amount
        budgeted = lah_budgets.getTotalBudgetedByYear(
            session["user_id"], budget['year'])

        # Generate the full, updatable budget data structure (name, amount for budget w/ all categories and their budgeted amounts)
        budget = lah_budgets.getUpdatableBudget(budget, session["user_id"])

        # Render the budget update page
        return render_template("updatebudget.html", income=income, budgeted=budgeted, budget=budget)


@app.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    # User reached route via POST
    if request.method == "POST":

        # Initialize user's actions
        userHasSelected_newCategory = False
        userHasSelected_renameCategory = False
        userHasSelected_deleteCategory = False

        # Initialize user alerts
        alert_newCategory = None
        alert_renameCategory = None
        alert_deleteCategory = None

        # Determine what action was selected by the user (button/form trick from: https://stackoverflow.com/questions/26217779/how-to-get-the-name-of-a-submitted-form-in-flask)
        if "btnCreateCategory" in request.form:
            userHasSelected_newCategory = True
        elif "btnRenameCategory" in request.form:
            userHasSelected_renameCategory = True
        elif "btnDeleteCategory" in request.form:
            userHasSelected_deleteCategory = True
        else:
            return apology("Doh! Spend Categories is drunk. Try again!")

        # Get new category details and create a new record in the DB
        if userHasSelected_newCategory:

            # Get the new name provided by user
            newCategoryName = request.form.get("createName").strip()

            # Make sure user has no more than 30 categories (note: 30 is an arbitrary value)
            categoryCount = len(
                lah_categories.getSpendCategories(session["user_id"]))
            if categoryCount >= 30:
                return apology("You've reached the max amount of categories")

            # Check to see if the new name already exists in the database (None == does not exist)
            categoryID = lah_categories.getCategoryID(newCategoryName)

            # Category exists in the database already
            if categoryID:

                # Make sure the user isn't trying to add a category they already have by passing in the users ID now (None == does not exists)
                existingID = lah_categories.getCategoryID(
                    newCategoryName, session["user_id"])
                if (existingID):
                    return apology("You already have '" + newCategoryName + "' category")
                # Add the category to the users account
                else:
                    lah_categories.addCategory_User(
                        categoryID, session["user_id"])

            # Category does not exist in the DB already - create a new category and then add it to the users account
            else:
                # Creates a new category in the DB
                newCategoryID = lah_categories.addCategory_DB(
                    newCategoryName)

                # Adds the category to the users account
                lah_categories.addCategory_User(
                    newCategoryID, session["user_id"])

            # Set the alert message for user
            alert_newCategory = newCategoryName

        # Get renamed category details and update records in the DB
        if userHasSelected_renameCategory:

            # Get the new/old names provided by user
            oldCategoryName = request.form.get("oldname").strip()
            newCategoryName = request.form.get("newname").strip()

            # Check to see if the *old* category actually exists in the database (None == does not exist)
            oldCategoryID = lah_categories.getCategoryID(oldCategoryName)

            # Old category does not exists in the database, throw error
            if oldCategoryID is None:
                return apology("The category you're trying to rename doesn't exist")

            # Check to see if the *new* name already exists in the database (None == does not exist)
            newCategoryID = lah_categories.getCategoryID(newCategoryName)

            # Category exists in the database already
            if newCategoryID:

                # Make sure the user isn't trying to rename to a category they already have by passing in the users ID now (None == does not exists)
                existingID = lah_categories.getCategoryID(
                    newCategoryName, session["user_id"])
                if existingID:
                    return apology("You already have '" + newCategoryName + "' category")

                # Get the new category name from the DB (prevents string upper/lowercase inconsistencies that can result from using the users input from the form instead of the DB)
                newCategoryNameFromDB = lah_categories.getSpendCategoryName(
                    newCategoryID)

                # Rename the category
                lah_categories.renameCategory(
                    oldCategoryID, newCategoryID, oldCategoryName, newCategoryNameFromDB, session["user_id"])

            # Category does not exist in the DB already - create a new category and then add it to the users account
            else:
                # Creates a new category in the DB
                newCategoryID = lah_categories.addCategory_DB(
                    newCategoryName)

                # Rename the category
                lah_categories.renameCategory(
                    oldCategoryID, newCategoryID, oldCategoryName, newCategoryName, session["user_id"])

            # Set the alert message for user
            alert_renameCategory = [oldCategoryName, newCategoryName]

        # Get deleted category details and update records in the DB
        if userHasSelected_deleteCategory:

            # Get the name of the category the user wants to delete
            deleteName = request.form.get("delete").strip()

            # Check to see if the category actually exists in the database (None == does not exist)
            categoryID = lah_categories.getCategoryID(deleteName)

            # Category does not exists in the database, throw error
            if categoryID is None:
                return apology("The category you're trying to delete doesn't exist")

            # Make sure user has at least 1 category (do not allow 0 categories)
            categoryCount = len(
                lah_categories.getSpendCategories(session["user_id"]))
            if categoryCount <= 1:
                return apology("You need to keep at least 1 spend category")

            # Delete the category
            lah_categories.deleteCategory(categoryID, session["user_id"])

            # Set the alert message for user
            alert_deleteCategory = deleteName

        # Get the users spend categories
        categories = lah_categories.getSpendCategories(session["user_id"])

        return render_template("categories.html", categories=categories, newCategory=alert_newCategory, renamedCategory=alert_renameCategory, deleteCategory=alert_deleteCategory)

    # User reached route via GET
    else:
        # Get the users spend categories
        categories = lah_categories.getSpendCategories(session["user_id"])

        # Get the budgets associated with each spend category
        categoryBudgets = lah_categories.getBudgetsSpendCategories(
            session["user_id"])

        # Generate a single data structure for storing all categories and their associated budgets
        categoriesWithBudgets = lah_categories.generateSpendCategoriesWithBudgets(
            categories, categoryBudgets)

        return render_template("categories.html", categories=categoriesWithBudgets, newCategory=None, renamedCategory=None, deleteCategory=None)


@app.route("/reports", methods=["GET"])
@login_required
def reports():
    return render_template("reports.html")


@app.route("/budgetsreport", methods=["GET"])
@app.route("/budgetsreport/<int:year>", methods=["GET"])
@login_required
def budgetsreport(year=None):
    # Make sure the year from route is valid
    if year:
        currentYear = datetime.now().year
        if not 2023 <= year <= currentYear:
            return apology(f"Please select a valid budget year: 2023 through {currentYear}")
    else:
        # Set year to current year if it was not in the route (this will set UX to display current years budgets)
        year = datetime.now().year

    # Generate a data structure that combines the users budgets and the expenses that have categories which match budgets
    budgets = lah_reports.generateBudgetsReport(session["user_id"], year)

    return render_template("budgetsreport.html", budgets=budgets, year=year)


@app.route("/monthlyreport", methods=["GET"])
@app.route("/monthlyreport/<int:year>", methods=["GET"])
@login_required
def monthlyreport(year=None):
    # Make sure the year from route is valid
    if year:
        currentYear = datetime.now().year
        if not 2023 <= year <= currentYear:
            return apology(f"Please select a valid budget year: 2023 through {currentYear}")
    else:
        # Set year to current year if it was not in the route (this will set UX to display current years report)
        year = datetime.now().year

    # Generate a data structure that combines the users monthly spending data needed for chart and table
    monthlySpending = lah_reports.generateMonthlyReport(
        session["user_id"], year)

    return render_template("monthlyreport.html", monthlySpending=monthlySpending, year=year)


@app.route("/spendingreport", methods=["GET"])
@app.route("/spendingreport/<int:year>", methods=["GET"])
@login_required
def spendingreport(year=None):
    # Make sure the year from route is valid
    if year:
        currentYear = datetime.now().year
        if not 2023 <= year <= currentYear:
            return apology(f"Please select a valid budget year: 2023 through {currentYear}")
    else:
        # Set year to current year if it was not in the route (this will set UX to display current years report)
        year = datetime.now().year

    # Generate a data structure that combines the users all-time spending data for chart and table
    spendingReport = lah_reports.generateSpendingTrendsReport(
        session["user_id"], year)

    return render_template("spendingreport.html", spending_trends_chart=spendingReport["chart"], spending_trends_table=spendingReport["table"], categories=spendingReport["categories"], year=year)


@app.route("/payersreport", methods=["GET"])
@app.route("/payersreport/<int:year>", methods=["GET"])
@login_required
def payersreport(year=None):
    # Make sure the year from route is valid
    if year:
        currentYear = datetime.now().year
        if not 2023 <= year <= currentYear:
            return apology(f"Please select a valid budget year: 2023 through {currentYear}")
    else:
        # Set year to current year if it was not in the route (this will set UX to display current years report)
        year = datetime.now().year

    # Generate a data structure that combines the users payers and expense data for chart and table
    payersReport = lah_reports.generatePayersReport(
        session["user_id"], year)

    return render_template("payersreport.html", payers=payersReport, year=year)


@app.route("/account", methods=["GET", "POST"])
@login_required
def updateaccount():
    # User reached route via POST
    if request.method == "POST":

        # Initialize user's actions
        userHasSelected_updateIncome = False
        userHasSelected_addPayer = False
        userHasSelected_renamePayer = False
        userHasSelected_deletePayer = False
        userHasSelected_updatePassword = False

        # Initialize user alerts
        alert_updateIncome = None
        alert_addPayer = None
        alert_renamePayer = None
        alert_deletePayer = None
        alert_updatePassword = None

        # Determine what action was selected by the user (button/form trick from: https://stackoverflow.com/questions/26217779/how-to-get-the-name-of-a-submitted-form-in-flask)
        if "btnUpdateIncome" in request.form:
            userHasSelected_updateIncome = True
        elif "btnSavePayer" in request.form:
            userHasSelected_addPayer = True
        elif "btnRenamePayer" in request.form:
            userHasSelected_renamePayer = True
        elif "btnDeletePayer" in request.form:
            userHasSelected_deletePayer = True
        elif "btnUpdatePassword" in request.form:
            userHasSelected_updatePassword = True
        else:
            return apology("Try again!")

        # Get new income details and update record in the DB
        if userHasSelected_updateIncome:

            # Get the new income amount
            newIncome = float(request.form.get("income").strip())

            # Update the users income
            updatedIncome = lah_account.updateIncome(
                newIncome, session["user_id"])

            # Render error message if the users income record could not be updated
            if updatedIncome != 1:
                return apology(updatedIncome["apology"])

            # Set the alert message for user
            alert_updateIncome = newIncome

        # Get new payer details and update record in the DB
        if userHasSelected_addPayer:

            # Get the new payers name from form
            newName = request.form.get("payerName").strip()

            # Add the payer
            newPayer = lah_account.addPayer(newName, session["user_id"])

            # Render error message if payer name is a duplicate of another payer the user has
            if newPayer != 1:
                return apology(newPayer["apology"])

            # Set the alert message for user
            alert_addPayer = newName

        if userHasSelected_renamePayer:

            # Get the old and new payer names from form
            oldName = request.form.get("oldpayer").strip()
            newName = request.form.get("newpayer").strip()

            # Rename the payer
            renamedPayer = lah_account.renamePayer(
                oldName, newName, session["user_id"])

            # Render error message if payer name is a duplicate of another payer the user has
            if renamedPayer != 1:
                return apology(renamedPayer["apology"])

            # Set the alert message for user
            alert_renamePayer = [oldName, newName]

        if userHasSelected_deletePayer:

            # Get the payer name from form
            name = request.form.get("delete").strip()

            # Delete the payer
            deletedPayer = lah_account.deletePayer(name, session["user_id"])

            # Render error message if the name could not be deleted
            if deletedPayer != 1:
                return apology(renamedPayer["apology"])

            # Set the alert message for user
            alert_deletePayer = name

        if userHasSelected_updatePassword:

            # Try updating the users password
            updatedPassword = lah_account.updatePassword(request.form.get(
                "currentPassword"), request.form.get("newPassword"), session["user_id"])

            # Render error message if the password could not be updated
            if updatedPassword != 1:
                return apology(updatedPassword["apology"])

            # Set the alert message for user
            alert_updatePassword = True

        # Get the users account name, income, payers, and stats
        user = lah_account.getAllUserInfo(session["user_id"])

        return render_template("account.html", username=user["name"], income=user["income"], payers=user["payers"], stats=user["stats"], newIncome=alert_updateIncome, addPayer=alert_addPayer, renamedPayer=alert_renamePayer, deletedPayer=alert_deletePayer, updatedPassword=alert_updatePassword)
    else:

        # Get the users account name, income, payers, and stats
        user = lah_account.getAllUserInfo(session["user_id"])

        return render_template("account.html", username=user["name"], income=user["income"], payers=user["payers"], stats=user["stats"], newIncome=None, addPayer=None, renamedPayer=None, deletedPayer=None, updatedPassword=None)


# Handle errors by rendering apology
def errorhandler(e):
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/uploadxls', methods=['POST'])
def upload_file():
    if 'xlsFile' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['xlsFile']

    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join("uploads", filename))  # Save the file to a folder named "uploads"
        
        # Get the user ID from the session
        userID = session["user_id"]

        added_expenses_count = lah_expenses.importExpensesFromFile(os.path.join("uploads", filename), userID)
        flash(f'Successfully imported {added_expenses_count} expense(s) from the file.')

    # Redirect to the expense history page
    return redirect(url_for('expensehistory'))

@app.route("/blog")
def blog():
    return render_template("blog.html")

if __name__ == '__main__':
    app.run(host='0.0.0.0')
