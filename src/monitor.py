import os
import requests
import datetime
import time
import json
from dotenv import load_dotenv

# Load local .env file
load_dotenv()

# Configuration
API_KEY = os.environ.get("SEATS_AERO_API_KEY")
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# Search Window: Today + 330 days
START_DATE = datetime.date.today()
END_DATE = START_DATE + datetime.timedelta(days=330)

# 1. Routes Reduced to JFK <-> HND only
ROUTES = [
    ("JFK", "HND"), 
    ("HND", "JFK")
]

# 2. Flight Filter Reduced to JL3/4/5/6
TARGET_FLIGHTS = {
    "JL3", "JL4", 
    "JL5", "JL6"
}

def normalize_flight_num(code):
    """
    Normalizes flight codes to match our set.
    Ex: "JL006" -> "JL6", "JL 004" -> "JL4"
    """
    if not code: return ""
    code = str(code).replace(" ", "").upper()
    
    # If it's just a number (e.g. 5), add JL
    if code.isdigit():
        return f"JL{int(code)}"
        
    # If it starts with JL, strip leading zeros
    if code.startswith("JL"):
        num_part = code[2:]
        if num_part.isdigit():
            return f"JL{int(num_part)}"
            
    return code

def check_flights():
    if not API_KEY:
        print("❌ Error: SEATS_AERO_API_KEY is missing.")
        return []

    url = "https://seats.aero/partnerapi/search"
    headers = {"Partner-Authorization": API_KEY}
    found_flights = []
    
    # Sources: American and Alaska
    sources = ["american", "alaska"]

    print(f"🔎 Scanning JFK-HND (JL 3/4/5/6)...")

    for origin, dest in ROUTES:
        for source in sources:
            params = {
                "origin_airport": origin,
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
                print(f"  ❌ Error {origin}->{dest} ({source}): {e}")
                continue

            for flight in data.get("data", []):
                # 1. Filter Airline (JAL)
                op_carrier = flight.get("OperatingAirlineCode") or ""
                if "JL" not in op_carrier: 
                    continue
                
                # 2. Filter Cabin (Business or First)
                j_avail = flight.get("JAvailable", False)
                f_avail = flight.get("FAvailable", False)
                if not (j_avail or f_avail):
                    continue

                # 3. Filter for Specific Flight Numbers
                flight_num_raw = flight.get("FlightNumber")
                flight_code = normalize_flight_num(flight_num_raw)

                if flight_code in TARGET_FLIGHTS:
                    flight['SourceProgram'] = source
                    flight['NormalizedFlightNum'] = flight_code
                    found_flights.append(flight)
            
            # Brief pause
            time.sleep(0.5)

    return found_flights

def notify(flights):
    if not flights:
        print("✅ No JL3/4/5/6 award space found.")
        return

    print(f"🚀 Found {len(flights)} seats! Sending Discord alert...")
    
    if not WEBHOOK_URL:
        print("⚠️ No Webhook URL set.")
        return

    embeds = []
    # Sort by date
    flights.sort(key=lambda x: x['Date'])

    for f in flights[:10]:
        date = f.get("Date")
        origin = f['Route']['OriginAirport']
        dest = f['Route']['DestinationAirport']
        flight_num = f.get("NormalizedFlightNum", "JL??")
        source = f.get("SourceProgram")
        
        # Cabin Display
        cabin_list = []
        if f.get("FAvailable"): cabin_list.append("FIRST")
        if f.get("JAvailable"): cabin_list.append("BIZ")
        cabin_str = " + ".join(cabin_list)

        # Cost Display
        cost = f.get("JMileage") or f.get("FMileage")
        cost_str = f"{int(cost):,} pts" if cost else "?"

        deep_link = f"https://seats.aero/{source}/{origin}/{dest}/{date}"
        color = 0xC8102E if source == 'american' else 0x004165

        embed = {
            "title": f"🇯🇵 {flight_num} {cabin_str} Found!",
            "description": f"**{origin} ⇄ {dest}**",
            "url": deep_link,
            "color": color,
            "fields": [
                {"name": "📅 Date", "value": date, "inline": True},
                {"name": "💰 Cost", "value": cost_str, "inline": True},
                {"name": "✈️ Flight", "value": flight_num, "inline": True}
            ]
        }
        embeds.append(embed)

    payload = {
        "content": "🚨 **JFK-HND A35K Space Detected** 🚨", 
        "embeds": embeds
    }
    
    try:
        requests.post(WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"❌ Failed to send Discord alert: {e}")

def save_to_json(flights):
    # Prepare the data for the frontend
    output_data = {
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "flights": []
    }

    for f in flights:
        output_data["flights"].append({
            "date": f.get("Date"),
            "route": f"{f['Route']['OriginAirport']} -> {f['Route']['DestinationAirport']}",
            "flight": f.get("NormalizedFlightNum", "N/A"),
            "cabin": "First" if f.get("FAvailable") else "Business",
            "source": f.get("SourceProgram"),
            "cost": f.get("JMileage") or f.get("FMileage"),
            "link": f"https://seats.aero/{f.get('SourceProgram')}/{f['Route']['OriginAirport']}/{f['Route']['DestinationAirport']}/{f.get('Date')}"
        })

    # Write to a file in the root directory (so GitHub Pages can find it)
    with open("results.json", "w") as f:
        json.dump(output_data, f, indent=4)
    print("✅ Saved results to results.json")

if __name__ == "__main__":
    flights = check_flights()
    notify(flights)
    save_to_json(flights)