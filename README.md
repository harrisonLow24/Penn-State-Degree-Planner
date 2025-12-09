# Penn State Course Planner

## Overview
A course planning tool designed to help Penn State students organize and manage their academic schedule.

## Features
- Course selection and scheduling
- Degree requirement tracking
- Prerequisite validation
- Schedule conflict detection

## Getting Started
1. Clone the repository
2. Install dependencies
    - Run `python -m pip install flask flask-sqlalchemy python-dotenv werkzeug`
3. Set up the database
    - Update the catalog folder with updated course data if necessary
    - Run `python import_catalog.py` to populate the database
4. Run the application
    - Run `python app.py` inside the frontend directory
4. Start planning your courses!

