"""
Interactive Autonomous AI Travel & Citizen FinTech Agent for Niffler.
Uses Gemini models with automatic fallback to execute multi-domain actions.
"""

from typing import Dict, Any, List, Optional
import json
import re
from .llm import UnifiedLLM
from .travel.flights import FlightRadar
from .travel.hotels import HotelRadar
from .travel.trains import IRCTCRadar
from .travel.buses import BusRadar
from .citizen.itr_optimizer import ITROptimizer
from .citizen.epf_explorer import EPFExplorer


class NifflerAgent:
    """Conversational & task-oriented AI agent for travel booking & citizen services."""

    SYSTEM_PROMPT = (
        "You are Niffler AI, a proactive, intelligent, and delightfully efficient Indian travel & citizen FinTech assistant. "
        "Inspired by the magical Niffler who sniffs out treasure and gold, you sniff out the lowest airfares, secret carrier deals, "
        "curated stays, IRCTC rail berths, bus routes, ITR tax savings (Old vs New regime), and EPF provident fund rules.\n\n"
        "Analyze the user query. If the query requires travel search, tax calculation, or EPF projection, extract the parameters and return a structured JSON response:\n"
        "{\n"
        '  "reply": "Conversational helpful summary answering the user with actionable tips.",\n'
        '  "action": {\n'
        '    "type": "SEARCH_FLIGHTS" | "SEARCH_HOTELS" | "SEARCH_TRAINS" | "SEARCH_BUSES" | "CALC_ITR" | "EXPLORE_EPF" | "NONE",\n'
        '    "origin": "DEL",\n'
        '    "destination": "BLR",\n'
        '    "city": "Jaipur",\n'
        '    "date": "2026-12-10",\n'
        '    "salary": 1200000,\n'
        '    "basic": 50000,\n'
        '    "tenure": 4.5\n'
        "  }\n"
        "}\n"
        "Always keep your tone warm, smart, and direct. Return valid JSON only."
    )

    def __init__(self):
        self.llm = UnifiedLLM()
        self.flight_radar = FlightRadar()
        self.hotel_radar = HotelRadar()
        self.train_radar = IRCTCRadar()
        self.bus_radar = BusRadar()
        self.itr_optimizer = ITROptimizer()
        self.epf_explorer = EPFExplorer()

    def process_query(self, message: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Process conversational user query, determine intent, and return message + action."""
        msg = message.strip()
        low = msg.lower()

        # Programmatic fast-checks for common city / airport abbreviations
        city_to_code = {
            "delhi": "DEL", "new delhi": "DEL", "mumbai": "BOM", "bombay": "BOM",
            "bangalore": "BLR", "bengaluru": "BLR", "goa": "GOI", "jaipur": "JAI",
            "hyderabad": "HYD", "chennai": "MAA", "madras": "MAA", "kolkata": "CCU",
            "calcutta": "CCU", "pune": "PNQ", "kochi": "COK", "ahmedabad": "AMD",
            "varanasi": "VNS", "lucknow": "LKO", "chandigarh": "IXC"
        }

        # 1. Direct LLM invocation
        prompt = f"User query: {msg}\nExtract intent, parameters, and return JSON response."
        try:
            raw_resp = self.llm.generate(prompt, system_prompt=self.SYSTEM_PROMPT, max_tokens=600)
            clean = re.sub(r"```json\s*|```", "", raw_resp).strip()
            parsed = json.loads(clean)
            if isinstance(parsed, dict) and "reply" in parsed:
                # Enhance action with normalized airport codes if applicable
                act = parsed.get("action") or {}
                if act.get("type") == "SEARCH_FLIGHTS":
                    orig = act.get("origin", "").lower()
                    dest = act.get("destination", "").lower()
                    if orig in city_to_code:
                        act["origin"] = city_to_code[orig]
                    if dest in city_to_code:
                        act["destination"] = city_to_code[dest]
                    act["origin"] = act.get("origin", "DEL")[:3].upper()
                    act["destination"] = act.get("destination", "BLR")[:3].upper()
                return parsed
        except Exception:
            pass

        # 2. Robust programmatic fallback if LLM unreachable / rate-limited
        # Flight pattern: from X to Y or X to Y flights
        flight_m = re.search(r"(?:from\s+)?([a-zA-Z\s]{3,15})\s+to\s+([a-zA-Z\s]{3,15})", low)
        if flight_m and any(w in low for w in ["flight", "fly", "airfare", "ticket", "cheap", "fare", "plane"]):
            raw_o = flight_m.group(1).strip()
            raw_d = flight_m.group(2).replace("flights", "").replace("flight", "").strip()
            o_code = city_to_code.get(raw_o, raw_o[:3].upper())
            d_code = city_to_code.get(raw_d, raw_d[:3].upper())
            return {
                "reply": f"Found the route: {o_code} → {d_code}! Let's compare official airline fares against MakeMyTrip, Ixigo, and Goibibo.",
                "action": {"type": "SEARCH_FLIGHTS", "origin": o_code, "destination": d_code}
            }

        # Hotel pattern
        hotel_m = re.search(r"(?:hotel|stay|resort|homestay|villa).*?(?:in\s+)?([a-zA-Z]{3,15})", low)
        if hotel_m:
            target_city = hotel_m.group(1).strip().title()
            return {
                "reply": f"Sniffing out curated hotels and boutique homestays in {target_city}. Switching to Stays view.",
                "action": {"type": "SEARCH_HOTELS", "city": target_city}
            }

        # Train pattern
        if any(w in low for w in ["train", "rail", "irctc", "tatkal", "berth", "pnr"]):
            return {
                "reply": "Opening IRCTC Rail Schedules & Tatkal radar. You can check seat availability and live PNR confirmation probability.",
                "action": {"type": "SEARCH_TRAINS", "origin": "NDLS", "destination": "MMCT"}
            }

        # Tax / ITR pattern
        if any(w in low for w in ["tax", "itr", "salary", "regime", "80c", "80d", "hra", "form 16"]):
            salary_num = 1200000
            num_m = re.search(r"(\d+[\d,]*)\s*(?:lakh|lakhs|l)?", low)
            if num_m:
                val = float(num_m.group(1).replace(",", ""))
                if "lakh" in low or val < 100:
                    salary_num = int(val * 100000)
                else:
                    salary_num = int(val)
            return {
                "reply": f"Analyzing tax optimization for ₹{salary_num:,} gross income. Let's compare Old vs New regime savings.",
                "action": {"type": "CALC_ITR", "salary": salary_num}
            }

        # EPF pattern
        if any(w in low for w in ["epf", "pf", "provident", "uan", "pension", "eps", "form 31", "form 19"]):
            return {
                "reply": "EPF Vault opened! Check 8.25% p.a. compound growth, retirement corpus projection, and Form 31 withdrawal rules.",
                "action": {"type": "EXPLORE_EPF"}
            }

        return {
            "reply": "Greetings! I'm Niffler AI. I can search the cheapest flights, find top hotels & homestays, check IRCTC trains, calculate ITR tax savings, and inspect EPF provident fund rules. What can I sniff out for you today?",
            "action": {"type": "NONE"}
        }
