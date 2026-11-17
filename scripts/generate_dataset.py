"""Generate the sample corpus of Warangal tourist reviews (datasets/warangal_reviews.csv).

Real review sites do not allow their reviews to be scraped and redistributed, so the
project ships a *synthetic but realistic* corpus built from phrase banks. Each attraction
has its own quality profile (for example Ramappa Temple scores high on heritage but low on
facilities), so the dashboard shows meaningful differences. Replace or extend this file
with real collected feedback (the CSV upload page accepts the same columns).

Run from the project folder:   python -m scripts.generate_dataset
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(__file__).resolve().parent.parent / "datasets" / "warangal_reviews.csv"
N_REVIEWS = 1500

# ---------- Attraction profiles ----------
# p = probability that a mention of the aspect is positive; weight = how popular the place is.
# feature = attraction-specific nouns used in the phrases for that aspect.
PLACES = {
    "Thousand Pillar Temple": dict(weight=16, aspects={
        "heritage": (0.93, ["the carved pillars", "the star-shaped platform", "the Nandi statue", "the stone carvings"]),
        "cleanliness": (0.55, ["the temple premises", "the toilets", "the surroundings"]),
        "crowd": (0.6, ["the darshan queue", "the temple"]),
        "access": (0.6, ["the parking area", "the approach road"]),
        "staff": (0.55, ["the guides", "the priests"]),
        "facilities": (0.45, ["drinking water", "shaded seating"]),
        "pricing": (0.85, ["the entry ticket"]),
        "safety": (0.85, ["the premises"])}),
    "Warangal Fort": dict(weight=15, aspects={
        "heritage": (0.88, ["the stone gateways", "the Kakatiya Kala Thoranam", "the fort ruins", "the sculptures"]),
        "cleanliness": (0.35, ["the fort area", "the toilets", "the open ground"]),
        "staff": (0.4, ["the guides", "the information boards"]),
        "facilities": (0.35, ["drinking water", "shade", "food stalls"]),
        "access": (0.5, ["the parking area", "the internal roads"]),
        "pricing": (0.8, ["the entry ticket"]),
        "safety": (0.6, ["the ruins", "the area in the evening"]),
        "nature": (0.7, ["the evening view", "the lawns"])}),
    "Ramappa Temple": dict(weight=18, aspects={
        "heritage": (0.96, ["the sculptures", "the floating bricks", "the dancer carvings", "the UNESCO heritage temple"]),
        "access": (0.4, ["the road from Warangal", "public transport", "the parking area"]),
        "facilities": (0.4, ["food options", "drinking water", "the restrooms"]),
        "cleanliness": (0.7, ["the temple complex", "the lawns"]),
        "staff": (0.65, ["the guides", "the ASI staff"]),
        "crowd": (0.7, ["the temple"]),
        "nature": (0.85, ["the Ramappa lake nearby", "the green surroundings"]),
        "pricing": (0.85, ["the entry fee"])}),
    "Bhadrakali Temple": dict(weight=14, aspects={
        "crowd": (0.35, ["the darshan queue", "the temple on Fridays", "festival days"]),
        "cleanliness": (0.5, ["the temple premises", "the toilets", "the lake bund"]),
        "nature": (0.85, ["the view of Bhadrakali lake", "the hilltop view"]),
        "heritage": (0.8, ["the goddess idol", "the old temple architecture"]),
        "staff": (0.55, ["the temple staff", "the priests"]),
        "access": (0.45, ["parking", "the steps"]),
        "facilities": (0.55, ["prasadam counters", "footwear stand", "drinking water"]),
        "safety": (0.8, ["the premises"])}),
    "Laknavaram Lake": dict(weight=13, aspects={
        "nature": (0.95, ["the hanging bridge", "the lake view", "the islands", "the sunset"]),
        "crowd": (0.4, ["the hanging bridge on weekends", "the boating counter"]),
        "facilities": (0.45, ["boating", "food stalls", "the cottages"]),
        "access": (0.45, ["the road", "transport from Warangal"]),
        "cleanliness": (0.5, ["the lake shore", "the toilets"]),
        "safety": (0.55, ["the bridge", "boating"]),
        "pricing": (0.6, ["the boating charges", "the entry ticket"])}),
    "Pakhal Lake": dict(weight=8, aspects={
        "nature": (0.92, ["the lake", "the forest", "the birds", "the sunset"]),
        "access": (0.35, ["the forest road", "public transport"]),
        "facilities": (0.3, ["food", "restrooms", "drinking water"]),
        "cleanliness": (0.7, ["the lake area"]),
        "safety": (0.6, ["the forest area", "the lake edge"]),
        "crowd": (0.85, ["the place"]),
        "staff": (0.5, ["the forest staff"])}),
    "Kakatiya Musical Garden": dict(weight=9, aspects={
        "facilities": (0.5, ["the musical fountain show", "the play area", "the lighting"]),
        "cleanliness": (0.45, ["the lawns", "the toilets"]),
        "nature": (0.7, ["the lawns", "the greenery"]),
        "pricing": (0.75, ["the entry ticket"]),
        "crowd": (0.55, ["the garden in the evening"]),
        "safety": (0.65, ["the garden at night"]),
        "staff": (0.5, ["the staff"])}),
    "Kakatiya Zoological Park": dict(weight=10, aspects={
        "nature": (0.7, ["the animals", "the greenery", "the walking paths"]),
        "cleanliness": (0.4, ["the enclosures", "the toilets", "the paths"]),
        "facilities": (0.45, ["drinking water", "the canteen", "benches"]),
        "pricing": (0.8, ["the entry ticket"]),
        "staff": (0.5, ["the zoo keepers", "the staff"]),
        "crowd": (0.6, ["the zoo on Sundays"]),
        "safety": (0.75, ["the enclosures"])}),
    "Padmakshi Temple": dict(weight=7, aspects={
        "heritage": (0.85, ["the Jain carvings", "the old temple"]),
        "nature": (0.88, ["the hilltop view", "the view of Hanamkonda"]),
        "access": (0.45, ["the steps", "parking"]),
        "crowd": (0.85, ["the temple"]),
        "cleanliness": (0.55, ["the temple premises"]),
        "facilities": (0.4, ["drinking water", "shade"])}),
}

# ---------- Phrase banks: {f} = attraction-specific feature ----------
PHRASES = {
    "heritage": {
        "positive": ["{F} is absolutely stunning and shows the skill of the Kakatiya craftsmen.",
                     "Loved {f}, every corner has some detail to admire.",
                     "A must visit for history lovers, {f} is breathtaking.",
                     "{F} is beautifully preserved and the architecture is amazing.",
                     "We were amazed by {f}, such fine work done centuries ago."],
        "negative": ["Parts of {f} are damaged and nobody seems to care.",
                     "{F} looks neglected and some carvings are broken.",
                     "Without proper boards it is hard to understand the history of {f}, very disappointing.",
                     "Sad to see people scribbling on {f}, the heritage is not protected."],
        "neutral": ["We spent about an hour looking at {f}.",
                    "{F} is mostly old stone structures.",
                    "There is {f} to see near the entrance."]},
    "cleanliness": {
        "positive": ["{F} was very clean and well maintained.",
                     "Surprisingly {f} was spotless and tidy.",
                     "Good to see {f} kept clean with dustbins everywhere.",
                     "Hygiene was good, {f} was clean."],
        "negative": ["{F} was dirty with plastic and garbage lying around.",
                     "{F} smelled terrible and was not cleaned at all.",
                     "Litter everywhere in {f}, very poor sanitation.",
                     "The toilets near {f} were filthy and unusable."],
        "neutral": ["There are dustbins near {f}.",
                    "{F} gets cleaned in the morning."]},
    "crowd": {
        "positive": ["{F} was peaceful and not crowded at all.",
                     "Very calm and serene atmosphere at {f}.",
                     "No rush at {f}, we could enjoy it peacefully.",
                     "Short queue at {f}, we were done quickly."],
        "negative": ["{F} was extremely crowded and we waited for hours.",
                     "Huge rush at {f}, too much pushing in the queue.",
                     "Waiting time at {f} was terrible, the queue was not managed.",
                     "{F} was overcrowded and noisy, hard to enjoy."],
        "neutral": ["{F} gets busy on weekends.",
                    "There was a normal queue at {f}."]},
    "access": {
        "positive": ["{F} is good and the place is easy to reach.",
                     "Getting there was easy, {f} is well connected.",
                     "Plenty of space in {f} and clear signboards.",
                     "{F} was smooth and convenient."],
        "negative": ["{F} is in bad condition with potholes everywhere.",
                     "Very difficult to reach, {f} is poor and there are no signboards.",
                     "{F} was a big problem, no proper parking at all.",
                     "No buses and {f} is very inconvenient for tourists."],
        "neutral": ["It takes about an hour to reach by road.",
                    "We came by car and used {f}."]},
    "pricing": {
        "positive": ["{F} is very affordable.",
                     "Totally worth the money, {f} is cheap.",
                     "{F} is reasonable for such a great place."],
        "negative": ["{F} is too expensive for what is offered.",
                     "Overpriced, {f} is not worth it.",
                     "They charged extra money for parking and {f}, felt like a waste."],
        "neutral": ["{F} can be bought at the counter.",
                    "There is {f} for adults and children."]},
    "facilities": {
        "positive": ["{F} was good and well organised.",
                     "Nice facilities, {f} was available and clean.",
                     "Enjoyed {f}, it was well managed.",
                     "{F} were excellent for families."],
        "negative": ["No {f} available, very poor facilities.",
                     "{F} was not working and nobody fixed it.",
                     "Facilities are bad, {f} is missing and we struggled in the heat.",
                     "{F} was poor and overpriced."],
        "neutral": ["There is {f} near the entrance.",
                    "{F} is available on some days."]},
    "staff": {
        "positive": ["{F} were very helpful and polite.",
                     "{F} explained everything nicely, very knowledgeable.",
                     "Friendly {f}, they guided us well."],
        "negative": ["{F} were rude and not helpful.",
                     "{F} asked for extra money and gave wrong information.",
                     "Nobody to guide us, {f} were missing."],
        "neutral": ["{F} are available at the gate.",
                    "We talked to {f} for directions."]},
    "nature": {
        "positive": ["{F} is breathtaking, so peaceful and green.",
                     "Loved {f}, perfect place for photos.",
                     "{F} was beautiful, the scenery is amazing.",
                     "The greenery and {f} made our day."],
        "negative": ["{F} was disappointing, polluted and dry.",
                     "{F} is spoiled by plastic waste.",
                     "Not much greenery left, {f} looks neglected."],
        "neutral": ["You can see {f} from the top.",
                    "{F} is nearby."]},
    "safety": {
        "positive": ["{F} felt safe with security around.",
                     "Good safety arrangements at {f}.",
                     "{F} is safe for families and children."],
        "negative": ["{F} felt unsafe, no railings or security.",
                     "No life jackets and {f} felt risky.",
                     "{F} is dangerous after dark, no police around."],
        "neutral": ["Security guards are present at {f}.",
                    "There are some railings at {f}."]},
}

OPENERS = ["Visited {p} with my family last weekend.", "Went to {p} on a trip from Hyderabad.",
           "Our college trip to {p} was on a Sunday.", "I visited {p} during the Dasara holidays.",
           "Stopped at {p} on our Warangal tour.", "Came to {p} with friends.", "", "", ""]
CLOSERS = {
    5: ["Highly recommended!", "Will definitely come again.", "One of the best places in Telangana.", "Loved it!"],
    4: ["Worth a visit.", "Good experience overall.", "Nice place to spend a few hours.", ""],
    3: ["Okay for a short visit.", "Average experience.", "It was fine.", ""],
    2: ["Needs improvement.", "Not a great experience.", "Authorities should take care of this.", ""],
    1: ["Very disappointing overall.", "Would not recommend right now.", "Terrible experience.", "Waste of time."],
}
NAMES = ["Ravi", "Sravani", "Akhil", "Divya", "Praveen", "Keerthi", "Naveen", "Swathi", "Rahul", "Anusha",
         "Kiran", "Lakshmi", "Suresh", "Bhavana", "Vamshi", "Harika", "Sai", "Pooja", "Mahesh", "Sneha",
         "Arjun", "Meghana", "Rohit", "Deepika", "Venkat", "Priyanka", "Tarun", "Shruthi", "Ajay", "Nikhitha",
         "John", "Emma", "Liam", "Sophie", "Raju", "Manasa", "Charan", "Haritha", "Srikanth", "Kavya"]
VISITOR_WEIGHTS = {"family": 34, "friends": 26, "solo": 10, "couple": 14, "school_trip": 9, "foreign_tourist": 7}
# Tourist season: more visits in winter and festival months.
MONTH_WEIGHTS = {1: 12, 2: 11, 3: 8, 4: 6, 5: 5, 6: 5, 7: 6, 8: 7, 9: 8, 10: 12, 11: 12, 12: 13}
START, END = date(2024, 1, 1), date(2026, 10, 31)


def cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def random_date() -> date:
    while True:
        d = START + timedelta(days=random.randint(0, (END - START).days))
        if random.random() < MONTH_WEIGHTS[d.month] / 13:
            return d


def make_review(place: str) -> dict:
    profile = PLACES[place]["aspects"]
    d = random_date()
    progress = (d - START).days / (END - START).days            # 0 -> 1 over the period
    keys = random.sample(list(profile), k=min(len(profile), random.choice([1, 2, 2, 3, 3, 4])))
    sentences, polarity = [], []
    for key in keys:
        p_pos, features = profile[key]
        if key in ("cleanliness", "facilities"):                 # gradual improvement after upgrades
            p_pos = min(p_pos + 0.12 * progress, 0.95)
        r = random.random()
        mood = "neutral" if r < 0.12 else ("positive" if r < 0.12 + 0.88 * p_pos else "negative")
        f = random.choice(features)
        sentences.append(cap(random.choice(PHRASES[key][mood]).replace("{F}", cap(f)).replace("{f}", f)))
        polarity.append({"positive": 1, "neutral": 0, "negative": -1}[mood])
    score = sum(polarity) / len(polarity)
    rating = max(1, min(5, round(3 + 2 * score + random.gauss(0, 0.55))))
    opener = random.choice(OPENERS).format(p=place)
    closer = random.choice(CLOSERS[rating])
    text = " ".join(s for s in [opener, *sentences, closer] if s)
    label = "positive" if rating >= 4 else "negative" if rating <= 2 else "neutral"
    return {"attraction": place, "reviewer_name": random.choice(NAMES),
            "visitor_type": random.choices(list(VISITOR_WEIGHTS), weights=VISITOR_WEIGHTS.values())[0],
            "rating": rating, "visit_date": d.isoformat(), "text": text, "label": label}


def main() -> None:
    places = list(PLACES)
    weights = [PLACES[p]["weight"] for p in places]
    rows = [make_review(random.choices(places, weights=weights)[0]) for _ in range(N_REVIEWS)]
    rows.sort(key=lambda r: r["visit_date"])
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    labels = {lbl: sum(r["label"] == lbl for r in rows) for lbl in ("positive", "neutral", "negative")}
    print(f"Wrote {len(rows)} reviews to {OUT}  {labels}")


if __name__ == "__main__":
    main()
