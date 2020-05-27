import os
import datetime

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    #Query information from finance database
    rows = db.execute("SELECT * FROM stocks WHERE user_id = :user", user=session["user_id"])

    cash = db.execute("SELECT cash FROM users WHERE id = :user", user=session["user_id"])[0]['cash']

    total = cash
    stocks = []
    for index, row in enumerate(rows):
        stock_info = lookup(row['symbol'])

        stocks.append(list((stock_info['symbol'], stock_info['name'], row['shares'], stock_info['price'], round(stock_info['price'] * row['shares'], 2))))
        total += stocks[index][4]

    return render_template("index.html", stocks=stocks, cash=round(cash, 2), total=round(total, 2))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        shares=int(request.form.get("shares"))
        symbol=lookup(request.form.get("symbol"))['symbol']

        #check availability
        if not lookup(symbol):
            return apology("Could not find your requested stock")

        price=lookup(symbol)['price']
        cash = db.execute("SELECT cash FROM users WHERE id = :user", user=session["user_id"])[0]["cash"]

        final_cash = cash - price * float(shares)

        #Check if user's got enough cash for transaction
        if final_cash < 0:
            return apology("You don't have enough money for the transation")

        #Check if user already bought stocks from the same company
        stock = db.execute("SELECT shares FROM stocks WHERE user_id = :user AND symbol = :symbol",
            user=session['user_id'], symbol=symbol)


        #First time buying stock, Insert new row in stocks table
        if not stock:
            db.execute("INSERT INTO stocks(user_id, symbol, shares) VALUES (:user, :symbol, :shares)",
                user=session["user_id"], symbol=symbol, shares=shares)

        #Update row into the stocks table
        else:
            shares += stock[0]['shares']

            db.execute("UPDATE stocks SET shares = :shares WHERE user_id = :user AND symbol = :symbol",
                user=session["user_id"], symbol=symbol, shares=shares)

        #Update user's cash
        db.execute("UPDATE users SET cash = :cash WHERE id = :user", cash=final_cash, user=session["user_id"])

        #Update history table
        db.execute("INSERT INTO transactions(user_id, symbol, shares, value) VALUES (:user, :symbol, :shares, :value)",
            user=session['user_id'], symbol=symbol, shares=shares, value=round(price*float(shares)))

        flash("Buying Successfull!")
        # Redirect user to login form
        return redirect("/")

    else:
        return render_template("buy.html")

@app.route("/addBalance", methods=["GET", "POST"])
@login_required
def addBalance():

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount"))
        except:
            return apology("Amount must be more than 0", 400)

        db.execute("UPDATE users SET cash = cash + :amount WHERE id = :user_id", user_id=session["user_id"], amount=amount)

        return redirect('/')
    else:
        return render_template("addBalance.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    rows = db.execute("SELECT * FROM transactions WHERE user_id = :user",
                            user=session["user_id"])

    transactions = []
    for row in rows:
        stock_list = lookup(row['symbol'])

        transactions.append(list((stock_list['symbol'], stock_list['name'], row['shares'], row['value'], row['date'])))

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/changePassword", methods=["GET", "POST"])
@login_required
def changePassword():
    """Allow user to change her password"""

    if request.method == "POST":

        # Ensure current password is not empty
        if not request.form.get("currentPassword"):
            return apology("Please enter current password", 400)

        # Query database for user_id
        rows = db.execute(
            "SELECT hash FROM users WHERE id = :user_id", user_id=session["user_id"])

        # Ensure current password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("currentPassword")):
            return apology("Invalid password", 400)

        # Ensure new password field is not empty
        if not request.form.get("new_password"):
            return apology("Must enter new password", 400)

        # Ensure new password confirmation field is not empty
        elif not request.form.get("new_password_confirmation"):
            return apology("Must re-enter new password confirmation", 400)

        # Ensure two passwords match
        elif request.form.get("new_password") != request.form.get("new_password_confirmation"):
            return apology("Passwords do not match", 400)

        # Update database
        hash = generate_password_hash(request.form.get("new_password"))
        rows = db.execute("UPDATE users SET hash = :hash WHERE id = :user_id",
                          user_id=session["user_id"], hash=hash)

        # Show flash
        flash("Password Changed!")

    return render_template("changePassword.html")

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))

        if not stock:
            return apology("Could not find any stock")

        return render_template("quote.html", stock=stock)
    else:
        return render_template("quote.html", stock=" ")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    #Discard any users id to create new account
    session.clear()

    if request.method == "POST":

        #Ensure user type his/her username
        if not request.form.get("username"):
            return apology("Must enter username", 403)

        #Ensure user type his/her password
        elif not request.form.get("password"):
            return apology("Must provide password", 403)

        #Ensure user's passwords matches
        elif request.form.get("password") != request.form.get("confirm-password"):
            return apology("Passwords do not match", 403)

        #Check user's username already exists or not in our database
        elif db.execute("SELECT * FROM users WHERE username = :username", username= request.form.get("username")):
            return apology("Username already exists", 403)

        db.execute("INSERT INTO users(username, hash) VALUES (:username, :hash)",
            username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))

        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # Remember current user
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":
        shares=int(request.form.get("shares"))
        symbol=request.form.get("symbol")
        price=lookup(symbol)["price"]
        value=round(price*float(shares))

        #Update Stocks table
        initial_shares = db.execute("SELECT shares FROM stocks WHERE user_id = :user AND symbol = :symbol",
            symbol=symbol, user=session["user_id"])[0]['shares']
        final_shares = initial_shares - shares

        #delete stock from table if the user sold all the stocks
        if final_shares == 0:
            db.execute("DELETE FROM stocks WHERE user_id = :user AND symbol = :symbol",
                symbol=symbol, user=session["user_id"])

        elif final_shares < 0:
            return apology("You own enough stocks")

        #update new value
        else:
            db.execute("UPDATE stocks SET shares = :shares WHERE user_id = :user AND symbol = :symbol",
                symbol=symbol, user=session["user_id"], shares=final_shares)

        #Update user's owned cash
        cash = db.execute("SELECT cash FROM users WHERE id = :user", user=session["user_id"])[0]['cash']

        final_cash = cash + price * float(shares)

        db.execute("UPDATE users SET cash = :cash WHERE id = :user", cash=final_cash, user=session["user_id"])

        #Update user's stock history
        db.execute("INSERT INTO transactions(user_id, symbol, shares, value) VALUES (:user, :symbol, :shares, :value)", user=session["user_id"],
            symbol=symbol, shares=shares, value=value)

        flash("Sold Successfully!")
        return redirect("/")

    else:

        rows = db.execute("SELECT symbol, shares FROM stocks WHERE user_id = :user", user=session["user_id"])

        #Create a dictionary with available stocks
        stocks = {}
        for row in rows:
            stocks[row['symbol']] = row['shares']

        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
