import os
import requests
import datetime
from dotenv import load_dotenv

# Load local .env file if it exists (for local dev)
load_dotenv()

# Configuration
API_KEY = os.environ.get("SEATS_AERO_API_KEY")
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
ORIGIN = "JFK"
# Monitoring both Haneda and Narita
DESTINATIONS = ["HND", "NRT"] 
# Start looking from today
START_DATE = datetime.date.today()
# Look 330 days out (Max AA window)
END_DATE = START_DATE + datetime.timedelta(days=330)

def check_flights():
    if not API_KEY:
        print("Error: SEATS_AERO_API_KEY is missing.")
        return []

    url = "https://seats.aero/partnerapi/search"
    headers = {"Partner-Authorization": API_KEY}
    found_flights = []

    # Check both American and Alaska programs
    sources = ["american", "alaska"]

    print(f"🔎 Checking {ORIGIN} to {DESTINATIONS}...")

    for dest in DESTINATIONS:
        for source in sources:
            params = {
                "origin_airport": ORIGIN,
                "destination_airport": dest,
                "start_date": START_DATE.strftime("%Y-%m-%d"),
                "end_date": END_DATE.strftime("%Y-%m-%d"),
                "source": source
            }

            try:
                resp = requests.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"❌ Error fetching {source} to {dest}: {e}")
                continue

            for flight in data.get("data", []):
                # Filter: Must be JAL (JL) and Business(J)/First(F)
                if flight.get("OperatingAirlineCode") == "JL":
                    if flight.get("JAvailable") or flight.get("FAvailable"):
                        # Add metadata for the notifier
                        flight['SourceProgram'] = source
                        found_flights.append(flight)

    return found_flights

def notify(flights):
    if not flights:
        print("✅ No new award space found.")
        return

    if not WEBHOOK_URL:
        print("⚠️ Flights found, but no Discord Webhook URL set.")
        for f in flights:
            print(f"  - Found {f['Date']} on {f['OperatingAirlineCode']}")
        return

    print(f"🚀 Found {len(flights)} flights! Sending Discord notification...")
    
    embeds = []
    # Discord limit: 10 embeds per message
    for f in flights[:10]:
        date = f.get("Date")
        origin = f['Route']['OriginAirport']
        dest = f['Route']['DestinationAirport']
        source = f.get("SourceProgram")
        
        cabin = "FIRST" if f.get("FAvailable") else "BUSINESS"
        cost = f.get("JMileage") or f.get("FMileage")
        cost_str = f"{int(cost):,} miles" if cost else "Unknown"

        # Direct link to Seats.aero search for verification
        deep_link = f"https://seats.aero/{source}/{origin}/{dest}/{date}"

        # Color: Red (AA) vs Teal (Alaska)
        color = 0xC8102E if source == 'american' else 0x004165

        embed = {
            "title": f"🇯🇵 JAL {cabin} Found!",
            "description": f"**{origin} ➡️ {dest}**",
            "url": deep_link,
            "color": color,
            "fields": [
                {"name": "📅 Date", "value": date, "inline": True},
                {"name": "💰 Cost", "value": cost_str, "inline": True},
                {"name": "🏦 Via", "value": source.title(), "inline": True}
            ]
        }
        embeds.append(embed)

    payload = {"content": "🚨 **JAL Award Availability Detected** 🚨", "embeds": embeds}
    
    try:
        r = requests.post(WEBHOOK_URL, json=payload)
        r.raise_for_status()
        print("✅ Notification sent successfully.")
    except Exception as e:
        print(f"❌ Failed to send Discord alert: {e}")

if __name__ == "__main__":
    flights = check_flights()
    notify(flights)