"""ChatGPT (OpenAI API) features with rule-based fallbacks so the app still works without a key."""
import json
import re

import streamlit as st

from core import menu
from core.config import secret

DEFAULT_MODEL = "gpt-4o-mini"
TOPICS = ["Taste", "Service", "Speed", "Price", "Atmosphere", "Order accuracy", "Pickup and curbside", "Menu variety"]


# ---------- client ----------
@st.cache_resource
def _client(api_key):
    from openai import OpenAI
    return OpenAI(api_key=api_key)


def enabled():
    return bool(secret("OPENAI_API_KEY"))


def model():
    return secret("OPENAI_MODEL", DEFAULT_MODEL)


def _create(messages, json_mode=False, stream=False, max_tokens=1200):
    kwargs = {"model": model(), "messages": messages, "max_completion_tokens": max_tokens, "stream": stream}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    return _client(secret("OPENAI_API_KEY")).chat.completions.create(**kwargs)


def complete(messages, max_tokens=1200):
    """Return model text, or None when AI is off or the call fails."""
    if not enabled():
        return None
    try:
        return _create(messages, max_tokens=max_tokens).choices[0].message.content
    except Exception as exc:
        st.session_state["ai_last_error"] = f"{type(exc).__name__}: {exc}"
        return None


def complete_json(system, user, max_tokens=1200):
    if not enabled():
        return None
    try:
        text = _create(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            json_mode=True, max_tokens=max_tokens,
        ).choices[0].message.content
        return _parse_json(text)
    except Exception as exc:
        st.session_state["ai_last_error"] = f"{type(exc).__name__}: {exc}"
        return None


def _parse_json(text):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\{.*\}", text or "", re.S)
        return json.loads(match.group(0)) if match else None


def stream(messages):
    """Yield response text chunks for st.write_stream."""
    try:
        for chunk in _create(messages, stream=True):
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as exc:
        st.session_state["ai_last_error"] = f"{type(exc).__name__}: {exc}"
        yield "Sorry, I can't reach the assistant right now. Please try again in a moment."


# ---------- sentiment ----------
POS = set("""good great love loved lovely excellent amazing delicious friendly fast perfect best awesome fresh tasty
nice enjoy enjoyed happy wonderful clean recommend helpful quick favorite smooth cozy warm fantastic polite
convenient easy rich creamy impressed kind welcoming efficient outstanding""".split())
NEG = set("""bad terrible awful slow cold rude dirty worst hate hated stale bitter burnt wrong late expensive
overpriced disappointing disappointed bland watery noisy messy unfriendly soggy forgot missing mistake
confusing long crowded lukewarm sour gross poor""".split())
NEGATORS = {"not", "no", "never", "isn't", "wasn't", "don't", "didn't", "hardly", "nothing"}
TOPIC_WORDS = {
    "Taste": ["taste", "flavor", "delicious", "bitter", "bland", "sweet", "burnt", "fresh", "stale", "creamy", "watery"],
    "Service": ["staff", "barista", "friendly", "rude", "service", "polite", "helpful", "cashier"],
    "Speed": ["fast", "slow", "wait", "quick", "late", "minutes", "line"],
    "Price": ["price", "expensive", "cheap", "value", "overpriced", "cost", "$"],
    "Atmosphere": ["clean", "noisy", "seating", "music", "cozy", "dirty", "table", "wifi", "atmosphere"],
    "Order accuracy": ["wrong", "missing", "forgot", "mistake", "incorrect"],
    "Pickup and curbside": ["curbside", "pickup", "pick up", "parking", "car"],
    "Menu variety": ["menu", "options", "variety", "selection", "vegan", "dairy"],
}


def _basic_sentiment(text):
    words = re.findall(r"[a-z']+", text.lower())
    pos = neg = 0
    for i, w in enumerate(words):
        flipped = any(prev in NEGATORS for prev in words[max(0, i - 2):i])
        if w in POS:
            neg, pos = (neg + 1, pos) if flipped else (neg, pos + 1)
        elif w in NEG:
            pos, neg = (pos + 1, neg) if flipped else (pos, neg + 1)
    score = 0.0 if pos + neg == 0 else (pos - neg) / (pos + neg)
    if pos and neg and abs(score) < 0.5:
        label = "mixed"
    elif score > 0.2:
        label = "positive"
    elif score < -0.2:
        label = "negative"
    else:
        label = "neutral"
    lowered = text.lower()
    topics = [t for t, keys in TOPIC_WORDS.items() if any(k in lowered for k in keys)]
    first = re.split(r"(?<=[.!?])\s", text.strip())[0][:140]
    replies = {
        "positive": "Thank you for the kind words. We're glad you enjoyed your visit and hope to see you again soon.",
        "negative": "Thank you for telling us. We're sorry we fell short, and we're sharing this with the team so we can fix it.",
        "mixed": "Thanks for the honest feedback. We're glad parts of your visit went well and we're working on the rest.",
        "neutral": "Thanks for sharing your feedback with us.",
    }
    return {
        "sentiment": label, "score": round(score, 2), "stars": round(3 + 2 * score, 1),
        "topics": topics, "summary": first, "reply": replies[label], "engine": "basic",
    }


def analyze_sentiment(text):
    system = (
        "You analyze customer reviews for Fairlane Coffee House. Return JSON with keys: "
        "sentiment (positive, neutral, negative, or mixed), score (number from -1 to 1), "
        "stars (number from 1 to 5, one decimal), topics (array chosen only from "
        f"{TOPICS}), summary (one plain sentence under 20 words), "
        "reply (a short, warm, specific reply from the manager, under 45 words, no emojis)."
    )
    result = complete_json(system, text, max_tokens=600)
    if not result:
        return _basic_sentiment(text)
    try:
        label = str(result.get("sentiment", "neutral")).lower()
        if label not in ("positive", "neutral", "negative", "mixed"):
            label = "neutral"
        return {
            "sentiment": label,
            "score": max(-1.0, min(1.0, float(result.get("score", 0)))),
            "stars": max(1.0, min(5.0, float(result.get("stars", 3)))),
            "topics": [t for t in result.get("topics", []) if t in TOPICS],
            "summary": str(result.get("summary", ""))[:200],
            "reply": str(result.get("reply", ""))[:400],
            "engine": "ai",
        }
    except (TypeError, ValueError):
        return _basic_sentiment(text)


# ---------- order priority ----------
URGENT_WORDS = ["urgent", "asap", "hurry", "rush", "emergency", "meeting in", "class in", "late for", "quick please"]
ALLERGY_WORDS = ["allerg", "nut", "peanut", "gluten", "celiac", "dairy free", "lactose", "epipen"]


def prioritize_order(notes, items_text, fulfillment):
    """Return (priority 0 to 3, reason). 3 is most urgent."""
    notes = (notes or "").strip()
    base = 1 if fulfillment == "curbside" else 0
    if not notes:
        return base, "Curbside order" if base else ""
    system = (
        "You triage cafe orders for the kitchen. Read the customer's note and return JSON with "
        "priority (integer 0 to 3: 0 normal, 1 slightly elevated, 2 high, 3 urgent), and "
        "reason (under 12 words, for the barista). Raise priority for time pressure or allergy safety. "
        "Allergy notes are at least 2. Do not raise priority just because the customer is polite or pushy."
    )
    result = complete_json(system, f"Fulfillment: {fulfillment}\nItems: {items_text}\nNote: {notes}", max_tokens=200)
    if result:
        try:
            return max(base, min(3, int(result.get("priority", 0)))), str(result.get("reason", ""))[:120]
        except (TypeError, ValueError):
            pass
    lowered = notes.lower()
    if any(w in lowered for w in ALLERGY_WORDS):
        return max(base, 2), "Allergy note: check ingredients"
    if any(w in lowered for w in URGENT_WORDS):
        return max(base, 2), "Customer is short on time"
    return base, "Special request"


# ---------- assistant ----------
def assistant_system_prompt(user_name, status_text, hours_text, history_text):
    return f"""You are the Fairlane Coffee House assistant, chatting with customers in the app.
Location: 19000 Hubbard Drive, Fairlane Center South, Dearborn, MI 48126. Email: fairlanecoffeehouse@gmail.com.
Right now: {status_text}
Hours:
{hours_text}

Menu (the only items we sell):
{menu.menu_as_text()}

What the app offers: order ahead for in-store pickup or curbside (customers tap "I'm here" when they park),
dine-in orders, table reservations for parties up to 6 (larger groups should email us), feedback, and careers.

Customer: {user_name or "a guest"}.
Recent orders: {history_text or "none on file"}.

Guidelines:
- Be brief and friendly. Two to five short sentences unless asked for detail. No emojis.
- Recommend only items from the menu and use their exact names so the app can show order buttons.
- Use the customer's order history to personalize suggestions when it helps.
- Quote prices and calories from the menu. We do not have full allergen data; for allergies, tell them to ask a barista.
- You cannot place orders, change orders, or book tables yourself. Point them to the Order or Reserve a table pages.
- If a question is unrelated to the cafe, answer briefly and steer back to how you can help."""


def basic_reply(message, status_text):
    """Keyword replies used when no API key is configured."""
    m = message.lower()
    if any(w in m for w in ["hour", "open", "close"]):
        return f"{status_text} See the Home page for the full weekly schedule."
    if any(w in m for w in ["reserv", "table", "book"]):
        return "You can book a table for up to 6 people on the Reserve a table page. For larger groups, email fairlanecoffeehouse@gmail.com."
    if any(w in m for w in ["curbside", "pickup", "pick up", "ahead"]):
        return "Order ahead on the Order page and choose in-store pickup or curbside. For curbside, tap I'm here on My orders when you park."
    named = menu.names_in_text(message)
    if named:
        cat, p = menu.find(named[0])
        return f"{p['Product Name']}: {p['Description']} It's {menu.price_label(p)}."
    if any(w in m for w in ["recommend", "suggest", "what should", "best"]):
        return "Try a Latte if you like mild and creamy, a Cortado for something stronger, or a Mango Boba Tea if you want something fruity."
    return "I can help with the menu, hours, ordering ahead, curbside pickup, and reservations. What would you like to know?"


# ---------- marketing ----------
def marketing_copy(kind, goal, audience, tone, channel, context):
    system = (
        "You write marketing copy for Fairlane Coffee House, a cafe at Fairlane Center in Dearborn, Michigan "
        "that uses AI to personalize orders, offers order-ahead with curbside pickup, and table reservations. "
        "Write plainly and specifically. No hashtag spam (three at most), no emojis unless the channel is social, "
        "no invented discounts unless the brief includes them. Only mention menu items that exist.\n\n"
        f"Menu:\n{menu.menu_as_text()}"
    )
    user = (f"Deliverable: {kind}\nGoal: {goal}\nAudience: {audience}\nTone: {tone}\nChannel: {channel}\n"
            f"Business context from our data:\n{context}\n\nWrite the deliverable now.")
    text = complete([{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens=1500)
    if text:
        return text
    return (f"{kind} draft (basic mode)\n\nFairlane Coffee House: your usual, ready when you are.\n"
            f"Order ahead in the app, pull up curbside, and we'll bring it out. Goal: {goal}. Audience: {audience}.\n"
            "Add an OpenAI API key in secrets to generate full AI copy.")


# ---------- hiring interview ----------
BASE_QUESTIONS = {
    "Barista": [
        "Tell us about a time you handled a rush of customers. What did you do to keep orders moving?",
        "A customer says their latte tastes wrong. Walk us through how you respond.",
        "What does good hospitality mean to you?",
        "How would you handle a curbside order when the customer arrives before it is ready?",
        "Which shifts are you available for, and why do you want to work at Fairlane?",
    ],
}


def interview_question(position, transcript, total):
    """Next interview question given the transcript [{'q':..,'a':..}]."""
    fallback = BASE_QUESTIONS.get(position, BASE_QUESTIONS["Barista"])
    n = len(transcript)
    if not enabled():
        return fallback[n % len(fallback)]
    convo = "\n".join(f"Q{i+1}: {t['q']}\nA{i+1}: {t['a']}" for i, t in enumerate(transcript))
    system = (
        f"You are a friendly hiring interviewer for Fairlane Coffee House screening a {position} candidate. "
        f"Ask question {n + 1} of {total}. Cover customer service, teamwork, speed under pressure, reliability, "
        "and role skills. Follow up on vague earlier answers when useful. Return only the question, one or two sentences. "
        "Do not ask about age, family, religion, health, national origin, or other protected characteristics."
    )
    text = complete([{"role": "system", "content": system}, {"role": "user", "content": convo or "Start the interview."}], max_tokens=300)
    return (text or fallback[n % len(fallback)]).strip()


def evaluate_interview(position, transcript):
    convo = "\n".join(f"Q: {t['q']}\nA: {t['a']}" for t in transcript)
    system = (
        f"You evaluate a screening interview for a {position} role at a cafe. Judge only job-related answers. "
        "Return JSON: score (1 to 10), recommendation (Advance, Hold, or Decline), strengths (array of short strings), "
        "concerns (array of short strings), summary (two sentences for the hiring manager)."
    )
    result = complete_json(system, convo, max_tokens=700)
    if not result:
        words = sum(len(t["a"].split()) for t in transcript)
        return {"score": None, "recommendation": "Needs review",
                "summary": f"Basic mode: {len(transcript)} answers, {words} words total. A manager should review the transcript.",
                "strengths": [], "concerns": []}
    return result


# ---------- insights ----------
def insight_brief(stats_text):
    system = (
        "You are a business analyst for Fairlane Coffee House. Given sales, fulfillment, reservation, and "
        "customer sentiment data, write a short brief: three findings, then three specific actions for next week. "
        "Use numbers from the data. Plain language, short sentences, no filler."
    )
    return complete([{"role": "system", "content": system}, {"role": "user", "content": stats_text}], max_tokens=900)
