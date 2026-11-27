"""
Lightweight embedded HTTP server & API backend for Niffler Web Portal.
"""

import http.server
import socketserver
import json
import os
import hmac
import hashlib
import secrets
import time
import urllib.parse
from pathlib import Path
from typing import Dict, Any

OTP_SECRET = (os.getenv("OTP_SECRET") or os.getenv("GEMINI_API_KEY") or "niffler-otp-dev-key").encode("utf-8")

from ..travel.flights import FlightRadar
from ..travel.hotels import HotelRadar
from ..travel.trains import IRCTCRadar
from ..travel.buses import BusRadar
from ..travel.booking_handoff import BookingHandoffEngine
from ..citizen.itr_optimizer import ITROptimizer
from ..citizen.epf_explorer import EPFExplorer
from ..agent import NifflerAgent
from ..config import NifflerConfig, BharatConfig, UserProfile


class NifflerAPIHandler(http.server.SimpleHTTPRequestHandler):
    """Handles both static dashboard files and dynamic JSON REST endpoints."""

    flight_radar = FlightRadar()
    hotel_radar = HotelRadar()
    train_radar = IRCTCRadar()
    bus_radar = BusRadar()
    handoff_engine = BookingHandoffEngine()
    itr_optimizer = ITROptimizer()
    epf_explorer = EPFExplorer()
    agent = NifflerAgent()

    def __init__(self, *args, **kwargs):
        static_dir = Path(__file__).parent / "static"
        super().__init__(*args, directory=str(static_dir), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # 1. Flight Search API (Skyscanner-Style Multi-Provider + Gemini 4 Hydrogen Agent)
        if path == "/api/flights":
            orig = qs.get("origin", ["DEL"])[0]
            dest = qs.get("destination", ["BLR"])[0]
            date = qs.get("date", [None])[0]
            direct = qs.get("direct", ["false"])[0].lower() == "true"
            pax = int(qs.get("pax", ["1"])[0] or 1)
            cabin = qs.get("cabin", ["E"])[0]
            with_meta = qs.get("with_meta", ["false"])[0].lower() == "true"
            if with_meta:
                res = self.flight_radar.search_flights_with_agent(
                    orig, dest, date, direct_only=direct, pax=pax, cabin=cabin
                )
                return self._send_json({
                    "flights": [f.__dict__ for f in res["flights"]],
                    "origin": res["origin"],
                    "destination": res["destination"],
                    "date": res["date"],
                    "offers": res["offers"],
                    "agent_model": res["agent_model"],
                    "ai_summary": res["ai_summary"],
                    "best_coupon_tip": res["best_coupon_tip"],
                    "agent_trace": res["agent_trace"],
                })
            flights = self.flight_radar.search_flights(orig, dest, date, direct_only=direct)
            return self._send_json([f.__dict__ for f in flights])

        # 2. Hotel Search API
        elif path == "/api/hotels":
            city = qs.get("city", ["GOA"])[0]
            budget = int(qs.get("budget", [0])[0]) if qs.get("budget") else None
            couple = qs.get("couple", ["false"])[0].lower() == "true"
            hotels = self.hotel_radar.search_hotels(city, max_budget=budget, couple_friendly_only=couple)
            return self._send_json([h.__dict__ for h in hotels])

        # 3. Train Search API
        elif path == "/api/trains":
            orig = qs.get("origin", ["NDLS"])[0]
            dest = qs.get("destination", ["MMCT"])[0]
            trains = self.train_radar.search_trains(orig, dest)
            return self._send_json([t.__dict__ for t in trains])

        # 4. Bus Search API
        elif path == "/api/buses":
            orig = qs.get("origin", ["BLR"])[0]
            dest = qs.get("destination", ["HYD"])[0]
            buses = self.bus_radar.search_buses(orig, dest)
            return self._send_json([b.__dict__ for b in buses])

        # 5. PNR Tracking API
        elif path == "/api/pnr":
            pnr = qs.get("pnr", ["2418901234"])[0]
            status = self.train_radar.check_pnr_status(pnr)
            return self._send_json(status.__dict__)

        # 6. EPF Explore API
        elif path == "/api/epf":
            basic = int(qs.get("basic", [50000])[0])
            tenure = float(qs.get("tenure", [4.5])[0])
            balance = int(qs.get("balance", [350000])[0])
            summary = self.epf_explorer.parse_or_simulate_account(
                monthly_basic_da=basic, years_of_service=tenure, starting_epf_balance=balance
            )
            rules = self.epf_explorer.check_withdrawal_eligibility(tenure, summary.employee_share_balance_inr)
            proj = self.epf_explorer.project_retirement_corpus(monthly_basic_da=basic, current_balance=summary.total_epf_balance_inr)
            return self._send_json({
                "summary": summary.__dict__,
                "eligibility": rules.__dict__,
                "projection": proj.__dict__
            })

        # Static assets
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        if parsed.path == "/api/auth/send-otp":
            raw_phone = "".join(c for c in str(data.get("phone", "")) if c.isdigit())[-10:]
            if len(raw_phone) != 10:
                return self._send_json({"error": "Please enter a valid 10-digit mobile number."}, status=400)
            otp = f"{secrets.randbelow(9000) + 1000}"
            exp = int(time.time()) + 300
            sig = hmac.new(OTP_SECRET, f"{raw_phone}:{otp}:{exp}".encode(), hashlib.sha256).hexdigest()
            return self._send_json({"sent": True, "phone": f"+91 {raw_phone}", "otp_token": f"{exp}.{sig}", "demo_otp": otp, "expires_in": 300})

        elif parsed.path == "/api/auth/verify-otp":
            raw_phone = "".join(c for c in str(data.get("phone", "")) if c.isdigit())[-10:]
            otp = str(data.get("otp", "")).strip()
            token = str(data.get("otp_token", ""))
            name = str(data.get("name", "")).strip() or f"Traveller ({raw_phone[-4:]})"
            try:
                exp_s, sig = token.split(".", 1)
                if int(time.time()) > int(exp_s):
                    return self._send_json({"verified": False, "error": "OTP expired. Please resend."}, status=400)
                expected = hmac.new(OTP_SECRET, f"{raw_phone}:{otp}:{exp_s}".encode(), hashlib.sha256).hexdigest()
                if hmac.compare_digest(sig, expected):
                    return self._send_json({"verified": True, "user": {"name": name, "phone": f"+91 {raw_phone}"}})
            except Exception:
                pass
            return self._send_json({"verified": False, "error": "Invalid OTP code."}, status=400)

        # 1. Booking Handoff
        elif parsed.path == "/api/booking/handoff":
            profile = UserProfile(
                full_name=str(data.get("passenger_name") or "").strip() or "Guest Traveller",
                age=int(data.get("passenger_age") or 28),
                gender=str(data.get("passenger_gender") or "Adult"),
                email=str(data.get("contact_email") or "").strip() or "guest@niffler.app",
                phone=str(data.get("contact_phone") or "").strip() or "+91 00000 00000",
            )
            engine = BookingHandoffEngine(profile)
            b_type = data.get("type", "flight")
            provider = str(data.get("provider") or "MakeMyTrip")
            provider_url = str(data.get("provider_url") or "")
            if b_type == "hotel":
                sess = engine.prepare_hotel_handoff(
                    data.get("hotel_name", "Hotel"),
                    data.get("city", "Goa"),
                    int(data.get("nights", 1)),
                    int(data.get("price", 4500)),
                    provider=provider,
                    provider_url=provider_url,
                )
            else:
                sess = engine.prepare_flight_handoff(
                    data.get("airline", "IndiGo"),
                    data.get("flight_number", "6E-2041"),
                    data.get("origin", "DEL"),
                    data.get("destination", "BLR"),
                    int(data.get("fare", 4800)),
                    travel_date=data.get("travel_date"),
                    provider=provider,
                    provider_url=provider_url,
                )
            return self._send_json(sess.__dict__)

        # 2. ITR Optimizer
        elif parsed.path == "/api/itr/optimize":
            salary = int(data.get("gross_salary", 1200000))
            sec80c = int(data.get("sec_80c", 150000))
            sec80d = int(data.get("sec_80d", 25000))
            hra = int(data.get("hra", 120000))
            tds = int(data.get("tds", 80000))
            pan = data.get("pan", "ABCDE1234F")
            name = str(data.get("name", "")).strip() or "Taxpayer"

            res = self.itr_optimizer.optimize_and_generate_itr(
                pan=pan,
                name=name,
                gross_salary=salary,
                sec_80c=sec80c,
                sec_80d=sec80d,
                hra_exemption=hra,
                tds_deducted=tds
            )
            return self._send_json({
                "pan": res.pan,
                "assessment_year": res.assessment_year,
                "old_regime": res.old_regime.__dict__,
                "new_regime": res.new_regime.__dict__,
                "recommended_regime": res.recommended_regime,
                "tax_savings_inr": res.tax_savings_inr,
                "itr_1_json": res.itr_1_json
            })

        elif route == "agent/chat":
            msg = str(data.get("message", "")).strip()
            history = data.get("history", [])
            resp = self.agent.process_query(msg, history=history)
            return self._send_json(resp)

        self.send_error(404, "Endpoint not found")

    def _send_json(self, data: Any, status: int = 200):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


BharatAPIHandler = NifflerAPIHandler


def start_server(host: str = "127.0.0.1", port: int = 8501):
    """Run local Niffler web server."""
    with socketserver.TCPServer((host, port), NifflerAPIHandler) as httpd:
        print(f"[*] Niffler Web Portal running at http://{host}:{port}")
        httpd.serve_forever()
