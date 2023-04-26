# **Project Background**

**_Budget Lah_** is a web-based application built with the Flask framework and Jinja2 templating engine, using PostgreSQL as its database. It is designed to help individuals and households track their expenses, create and manage budgets, and generate reports for better financial planning.

# **Project Description**
This project involves elements of Create-Read-Update-Delete (CRUD) to create an account for Users to track their expenses. Create multiple budgets for yourself to track spending. 

Features:
- Quick and bulk expensing
- Budget creation and automatic tracking of expenses per budget
- Custom spend categories
- Dashboard with dynamic reporting
- Detailed reports that break down spending
- Add additional payers for tracking expenses across multiple people
- Export your data directly into raw, CSV, and Excel
- Responsive design - compatible with all major browsers and devices
- Upload expenses by scanning your downloaded bank statements
- Mobile Responsive


# **Timeframe**
7 Working Days

# **Deployment** 
https://budget-lah.onrender.com

# **Technologies Utilized**
- HTML
- CSS
- Javascript
- Python
- Jinja Framework (FrontEnd)
- Flask (BackEnd)
- PostgresSQL (Database)

# User Stories
| As a  user, when I...                    |  I want to be able to...                
| :--------------------------------------- |:-----------------------------------------------|   
| Access My Account                        |  - Update my income <br>- Add,Update and Delete payers <br>- Change Password
| View My Dashboard                        |  - See my last 5 expenses<br>- See an overview of my budgets <br>- See myself and other payer's spending
| Access Expenses                          |  - Add multiple expenses<br>- Upload UOB Credit Card Statement<br>- Updated / Delete expenses
| Access Budgets                           |  - Add, Update and Delete Budgets <br>- Tag categories to Budgets
| Acess Categories                         |  - Add, Update and Delete Categories to tag to expenses
| Acess Reports                            |  - See my spending categories, budget, monthly spending and payer reports <br>- Export them to Excel



### _Entity Relationship Diagram (ERD)_
<img width="646" alt="Screenshot 2023-04-25 at 9 44 23 AM" src="https://user-images.githubusercontent.com/68887503/234154174-f15bdb7d-f3a9-40d3-bb12-55235f6c2816.png">

# **Code Snipet**
Implemented data extraction, using python to convert it into a format that can be uploaded into a database
<img width="937" alt="Screenshot 2023-04-25 at 9 57 58 AM" src="https://user-images.githubusercontent.com/68887503/234155926-7701a8ed-65c0-4fcc-a177-39e980d0bfa7.png">



# **Key Takeaways**

- Test, Test and Test
- Plan Database
- Deployment first is key

# **Future Works**
- Support bank statments from multiple banks. Currently only supports UOB Credit Card Statments

