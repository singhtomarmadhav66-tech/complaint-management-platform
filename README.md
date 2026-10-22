# Campus Complaint Management Platform — Milestone 3 (Step 1 + Step 2)

**Step 1** set up the project, the database, and login with roles
(student, officer, hod, committee, admin).

**Step 2** (new) adds:
- Complaint submission form (category, title, description, optional
  file attachment, optional anonymous checkbox).
- Automatic routing: each category is linked to a handler role
  (officer / hod / committee), and the new complaint is auto-assigned
  to whichever user of that role currently has the fewest open
  complaints.
- Student dashboard showing "My Complaints" with status.
- Officer/HOD/Committee dashboard showing complaints assigned to them.
- Admin dashboard showing all complaints.
- A complaint detail page with full history, and a form for the
  assigned handler (or admin) to update status and add a remark.
- Anonymous complaints hide the student's name from the handler (but
  not from the student themself or the admin).

## What's in the project
- `app.py` — Flask app, all database models (User, Category, Complaint,
  Attachment, ComplaintHistory), and all routes.
- `templates/` — HTML pages (Bootstrap).
- `static/uploads/` — uploaded complaint attachments are stored here.
- `requirements.txt` — Python packages needed.

## How to run this (step by step)

1. **Open the folder in VS Code.**
   File → Open Folder → select `complaint_platform`.

2. **Open a terminal in VS Code** (Terminal → New Terminal) and create a
   virtual environment:
   ```
   python -m venv venv
   ```

3. **Activate it:**
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`

   You should see `(venv)` appear at the start of the terminal line.

4. **Install the required packages:**
   ```
   pip install -r requirements.txt
   ```

5. **Create (or reset) the database:**
   ```
   flask --app app init-db
   ```
   If you already have `complaints.db` from Step 1, delete that file
   first so the new tables (Complaint, Attachment, ComplaintHistory)
   get created. This command adds the complaint categories and one
   test account per role:

   | Role      | Email                     | Password     |
   |-----------|---------------------------|--------------|
   | Admin     | admin@college.edu         | admin123     |
   | Officer   | officer@college.edu       | officer123   |
   | HOD       | hod@college.edu           | hod123       |
   | Committee | committee@college.edu     | committee123 |

6. **Run the app:**
   ```
   python app.py
   ```
   Open your browser at **http://127.0.0.1:5000**

7. **Try the full flow:**
   - Register a new student account and log in.
   - Click "+ Submit Complaint", pick a category (e.g. "Hostel"),
     fill in a title/description, and submit.
   - Log out, log in as `officer@college.edu` — the complaint should
     appear in "Complaints Assigned to Me" (because Hostel routes to
     the officer role).
   - Open the complaint, change its status (e.g. to "In Progress"),
     add a remark, and save.
   - Log out, log back in as the student — the updated status and
     your remark should be visible in the complaint's history.
   - Try a category like "Faculty / Professor Related" (routes to
     `hod@college.edu`) or "Women Safety and Harassment" (routes to
     `committee@college.edu`) to see routing change by category.
   - Try submitting with the "Submit anonymously" box checked, then
     view it as the officer — the student's name should be hidden.

## If something goes wrong
- `flask: command not found` → make sure `(venv)` is active, then
  reinstall: `pip install -r requirements.txt`.
- Port already in use → close other running `python app.py` windows,
  or change the port: `app.run(debug=True, port=5001)`.
- To start fresh, delete `complaints.db` and run `flask --app app init-db` again.

## Step 3 (new): Admin Panel
- Logged in as admin, click **"Admin Panel"** in the top navigation bar.
- **Dashboard** — shows total / open / resolved / overdue complaint counts.
- **All Complaints** — every complaint in the system, click any row to open it.
- **Manage Users** — see every user and change their role (e.g. turn a
  student into an officer).
- **Manage Categories** — edit each category's default priority, SLA
  hours, which role it routes to, and whether it's confidential.
- "Back" links have also been added on the complaint form, complaint
  detail page, and all admin pages, so you're never stuck without a
  way back.

## Step 4 (new): Confidential Protection + Feedback/Reopen

**Confidential protection** — for categories marked "Confidential"
(Women Safety, Ragging), only the student who filed it, the
committee, or the admin can ever open the complaint — even if it
somehow ended up assigned to the wrong role. Try it: log in as
`officer@college.edu` and open a Ragging/Safety complaint's URL
directly — you should get a "Forbidden" page.

**Feedback and reopen** — once a handler marks a complaint
"Resolved", the student sees two options on the complaint page:
- Rate it 1–5 stars with an optional comment → this closes the
  complaint.
- "Reopen Complaint" with a reason → this sets it back to
  "In Progress" so the handler can keep working on it.

Test it: as a handler, set a complaint's status to "Resolved" and
save. Log in as the student who filed it, open that complaint, and
you'll see the feedback/reopen section.

## What's next (Step 5)
Email/in-app notifications, and automatic escalation for overdue
complaints (using a scheduler to check deadlines).
