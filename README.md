# Fairlane Coffee House

A Streamlit web app for a hypothetical café at Fairlane Center in Dearborn, Michigan. It covers day-to-day
operations (menu, ordering, pickup, reservations, staff queues) and uses ChatGPT through the OpenAI API for
customer chat, sentiment analysis, order triage, hiring interviews, marketing copy, and business insights.

## Features

**Customers**
- Live open or closed status and weekly hours
- Menu built from `data/menu.json`, with sizes, flavors, calories, and prices
- Order ahead for in-store pickup or curbside, in 15-minute slots up to 7 days out, with slot limits so the kitchen isn't overloaded
- Curbside check-in: tap I'm here with a parking spot and the service desk is alerted
- Change or cancel an order until the kitchen starts it; reorder past orders in one tap
- Table reservations for parties up to 6, with automatic table assignment, rescheduling, and cancellation
- Ask Fairlane: a ChatGPT assistant that knows the menu, hours, and the customer's order history, with order buttons for any item it suggests
- Feedback with instant sentiment analysis and a reply from the café
- Careers page with an AI screening interview
- Accounts with registration, profile editing, and password reset by emailed link or security question

**Staff**
- Kitchen queue sorted by curbside arrivals, AI priority, then due time; scheduled orders appear 20 minutes before pickup
- Service desk for handoffs, curbside arrivals, and the day's reservations (seat, finish, no-show)

**Managers**
- Insights: revenue, top items, busy hours, fulfillment mix, sentiment trends, topics, and each regular's favorite item
- Score reviews from text: paste reviews or upload a CSV, get sentiment and a 1 to 5 score, download results
- AI brief with findings and suggested actions
- Marketing studio that drafts copy from real sales and review data
- Hiring dashboard with interview transcripts and AI scores
- User and role management

## AI features and where they live

| Feature | File | What ChatGPT does |
|---|---|---|
| Customer chat | `views/assistant.py` | Answers questions and recommends items using the menu and order history |
| Sentiment analysis | `core/ai.py` `analyze_sentiment` | Labels feedback, scores it 1 to 5, tags topics, drafts a reply |
| Order triage | `core/ai.py` `prioritize_order` | Reads order notes and flags urgent or allergy orders for the kitchen |
| Hiring interview | `views/careers.py` | Asks adaptive questions, then scores the candidate |
| Marketing | `views/marketing.py` | Drafts slogans, posts, emails, and promotions |
| Insights brief | `views/insights.py` | Turns sales and sentiment data into findings and actions |

Without an API key the app still runs. Each feature falls back to a simple rule-based version and a note appears on the page.

## Deploy on Streamlit Community Cloud

1. Create a new GitHub repository and upload everything in this folder, including the hidden `.streamlit` folder. Do not upload a real `secrets.toml`.
2. Go to [share.streamlit.io](https://share.streamlit.io), choose **Create app**, pick the repository and branch, and set the main file to `streamlit_app.py`.
3. Open **Advanced settings > Secrets** and paste the contents of `.streamlit/secrets.toml.example` with your own values. At minimum set `OPENAI_API_KEY`, and change the manager and staff passwords.
4. Deploy. After the first deploy, copy the app's URL into the `APP_URL` secret so password reset links point to the right place.

### Password reset email (optional)

Reset links need an SMTP account. With Gmail:
1. Turn on 2-Step Verification for the Gmail account.
2. Create an App Password (Google Account > Security > App passwords).
3. Put the 16-character app password in the `[smtp]` secrets table.

If SMTP isn't set up, users reset their password with the security question they chose at sign-up.

## Logins

The first run creates two accounts from the `[admin]` and `[staff]` secrets. If those aren't set, the defaults are:

| Role | Username | Password |
|---|---|---|
| Manager | manager | Fairlane#2026 |
| Staff | barista | Barista#2026 |

Change these through secrets before sharing the app. Managers can promote any user to staff or manager on the Users and roles page.

To fill the charts for a demo, open **Insights > Demo data > Load sample data**. Sample customers use the password `Sample#2026`.

## Data storage

The app stores everything in a SQLite file at `data/fairlane.db`. Streamlit Community Cloud does not keep files between restarts, so data resets when the app reboots or redeploys. That's fine for a class demo. For a real café, point `core/db.py` at a hosted database such as Supabase Postgres or Google Sheets.

## Run locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit it
streamlit run streamlit_app.py
```

## Project structure

```
streamlit_app.py        entry point: setup, sidebar login, role-based navigation
core/
  ai.py                 OpenAI calls and rule-based fallbacks
  auth.py               accounts, roles, hashing, password reset
  db.py                 SQLite schema and helpers
  feedback.py           feedback storage
  hours.py              business hours and Dearborn local time
  mailer.py             SMTP email
  menu.py               menu loading and pricing
  orders.py             cart, pickup slots, order lifecycle, staff queues
  reservations.py       tables, availability, bookings
  sample_data.py        demo data generator
  ui.py                 shared layout and access checks
views/                  one file per page
data/menu.json          the menu
```

## Changing the business

- Menu: edit `data/menu.json`. Use a single value for one-size items or a list for sizes, calories, and prices.
- Hours: `HOURS` in `core/hours.py`.
- Tables and seating length: `TABLES` and `SEATING_MINUTES` in `core/reservations.py`.
- Pickup slot size and capacity: `SLOT_MINUTES` and `SLOT_CAPACITY` in `core/orders.py`.
- Model: set `OPENAI_MODEL` in secrets.
