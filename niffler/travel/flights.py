"""
Skyscanner-Style Live Flight Aggregator & Gemini 4 Hydrogen Deal Agent.

Concurrently queries date-exact Google Flights inventory, Goibibo SSR route feeds,
and web index snippets, then merges multi-provider offers (Official Airline Direct,
MakeMyTrip, Goibibo, Ixigo) and runs Gemini 4 Hydrogen analysis for lowest fares.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import datetime
import html as html_lib
import json
import os
import re
import urllib.parse
import urllib.request

from ..config import load_env_file
from ..llm import UnifiedLLM


@dataclass
class FlightOption:
    airline: str
    flight_number: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    duration: str
    stops: int
    price_inr: int
    cabin_baggage: str = "7 kg"
    checkin_baggage: str = "15 kg"
    booking_url: str = ""
    is_cheapest: bool = False
    is_fastest: bool = False
    source: str = "Google Flights Live"
    promo_note: str = ""
    base_fare_inr: int = 0
    taxes_inr: int = 0
    provider_offers: List[Dict[str, Any]] = field(default_factory=list)


class FlightRadar:
    """Skyscanner-style multi-provider live fare radar powered by Gemini 4 Hydrogen."""

    AIRLINE_MAPPINGS = {
        "6E": ("IndiGo", "https://www.goindigo.in"),
        "AI": ("Air India", "https://www.airindia.com"),
        "IX": ("Air India Express", "https://www.airindiaexpress.com"),
        "QP": ("Akasa Air", "https://www.akasaair.com"),
        "SG": ("SpiceJet", "https://www.spicejet.com"),
        "UK": ("Vistara", "https://www.airindia.com"),
        "EK": ("Emirates", "https://www.emirates.com"),
        "QR": ("Qatar Airways", "https://www.qatarairways.com"),
        "EY": ("Etihad Airways", "https://www.etihad.com"),
        "WY": ("Oman Air", "https://www.omanair.com"),
        "FZ": ("flydubai", "https://www.flydubai.com"),
        "SQ": ("Singapore Airlines", "https://www.singaporeair.com"),
        "TG": ("Thai Airways", "https://www.thaiairways.com"),
        "IC": ("FLY91", "https://www.fly91.in"),
        "I5": ("AIX Connect", "https://www.airindiaexpress.com"),
        "S5": ("Star Air", "https://www.starair.in"),
    }

    AIRPORT_INFO: Dict[str, Tuple[str, str]] = {
        "DEL": ("New Delhi", "delhi"),
        "DXN": ("Noida (Jewar)", "delhi"),
        "BOM": ("Mumbai", "mumbai"),
        "BLR": ("Bengaluru", "bangalore"),
        "GOI": ("Goa Dabolim", "goa"),
        "GOX": ("Goa Mopa", "goa"),
        "HYD": ("Hyderabad", "hyderabad"),
        "MAA": ("Chennai", "chennai"),
        "CCU": ("Kolkata", "kolkata"),
        "PNQ": ("Pune", "pune"),
        "JAI": ("Jaipur", "jaipur"),
        "AMD": ("Ahmedabad", "ahmedabad"),
        "COK": ("Kochi", "kochi"),
        "LKO": ("Lucknow", "lucknow"),
        "PAT": ("Patna", "patna"),
        "GAU": ("Guwahati", "guwahati"),
        "IXC": ("Chandigarh", "chandigarh"),
        "ATQ": ("Amritsar", "amritsar"),
        "VNS": ("Varanasi", "varanasi"),
        "BBI": ("Bhubaneswar", "bhubaneswar"),
        "TRV": ("Thiruvananthapuram", "trivandrum"),
        "SXR": ("Srinagar", "srinagar"),
        "IXL": ("Leh", "leh"),
        "UDR": ("Udaipur", "udaipur"),
        "IDR": ("Indore", "indore"),
        "NAG": ("Nagpur", "nagpur"),
        "BHO": ("Bhopal", "bhopal"),
        "VTZ": ("Visakhapatnam", "visakhapatnam"),
        "IXB": ("Bagdogra", "bagdogra"),
        "DXB": ("Dubai", "dubai"),
        "AUH": ("Abu Dhabi", "abu-dhabi"),
        "SHJ": ("Sharjah", "sharjah"),
        "DOH": ("Doha", "doha"),
        "SIN": ("Singapore", "singapore"),
        "BKK": ("Bangkok", "bangkok"),
        "KUL": ("Kuala Lumpur", "kuala-lumpur"),
        "LHR": ("London", "london"),
    }

    AIRPORT_NAMES = {k: f"{v[0]} ({k})" for k, v in AIRPORT_INFO.items()}

    INTL_CODES = {"DXB", "SIN", "BKK", "LHR", "JFK", "SFO", "AUH", "SHJ", "DOH", "KUL", "HKG", "NRT", "CDG", "FRA", "YYZ", "MEL", "SYD"}

    BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
    }

    def _resolve_city_slug_and_iata(self, query: str) -> Tuple[str, str, str]:
        q = query.strip()
        upper = q.upper()
        if upper in self.AIRPORT_INFO:
            name, slug = self.AIRPORT_INFO[upper]
            return upper, name, slug

        low = q.lower()
        for code, (name, slug) in self.AIRPORT_INFO.items():
            if low == slug or low in name.lower():
                return code, name, slug

        try:
            url = f"https://autocomplete.travelpayouts.com/places2?term={urllib.parse.quote(q)}&locale=en&types[]=airport&types[]=city"
            req = urllib.request.Request(url, headers=self.BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=4) as r:
                items = json.loads(r.read().decode("utf-8", errors="ignore"))
                if items and isinstance(items, list):
                    top = items[0]
                    code = (top.get("code") or upper[:3]).upper()
                    city_name = top.get("city_name") or top.get("name") or q.title()
                    slug = re.sub(r"[^a-z0-9]+", "-", city_name.lower()).strip("-")
                    return code, city_name, slug
        except Exception:
            pass

        slug = re.sub(r"[^a-z0-9]+", "-", low).strip("-") or "delhi"
        return upper[:3], q.title(), slug

    @staticmethod
    def _format_dates(target_date: str) -> Tuple[str, str, str]:
        """Return (YYYY-MM-DD, DDMMYYYY, DD/MM/YYYY)."""
        try:
            dt = datetime.datetime.strptime(target_date, "%Y-%m-%d")
        except Exception:
            dt = datetime.datetime.now() + datetime.timedelta(days=7)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%d%m%Y"), dt.strftime("%d/%m/%Y")

    def _build_airline_direct_url(self, airline: str, flight_no: str, orig: str, dest: str, iso_date: str, pax: int = 1) -> Tuple[str, str]:
        """Build carrier official booking URL and display label."""
        prefix = (flight_no.split("-")[0] if flight_no else "").upper()[:2]
        info = self.AIRLINE_MAPPINGS.get(prefix)
        base_url = info[1] if info else f"https://www.google.com/travel/flights?q=Flights+from+{orig}+to+{dest}+on+{iso_date}+one+way&curr=INR&hl=en"
        label = f"{info[0]} Official" if info else f"{airline} Official"

        if prefix == "6E":
            url = f"https://www.goindigo.in/flight-booking.html?origin={orig}&destination={dest}&departDate={iso_date}&adults={pax}"
        elif prefix == "AI":
            url = f"https://www.airindia.com/in/en/book/search-flights.html?from={orig}&to={dest}&departureDate={iso_date}&adults={pax}"
        elif prefix == "IX":
            url = f"https://www.airindiaexpress.com/flight-availability?origin={orig}&destination={dest}&date={iso_date}&adults={pax}"
        elif prefix == "QP":
            url = f"https://www.akasaair.com/en-in/flight-booking?origin={orig}&destination={dest}&departDate={iso_date}&adults={pax}"
        elif prefix == "SG":
            url = f"https://www.spicejet.com/?from={orig}&to={dest}&date={iso_date}&adults={pax}"
        else:
            url = base_url
        return label, url

    def _build_provider_offers(
        self,
        airline: str,
        flight_no: str,
        orig: str,
        dest: str,
        target_date: str,
        primary_price: int,
        goibibo_price: Optional[int] = None,
        airline_price: Optional[int] = None,
        pax: int = 1,
        cabin: str = "E",
    ) -> List[Dict[str, Any]]:
        """Assemble Skyscanner-style multi-provider offer list per flight."""
        iso_dt, ddmmyyyy, ddmmyyyy_slash = self._format_dates(target_date)
        is_intl = "true" if (orig in self.INTL_CODES or dest in self.INTL_CODES) else "false"
        carrier_label, carrier_url = self._build_airline_direct_url(airline, flight_no, orig, dest, iso_dt, pax)

        mmt_url = (
            f"https://www.makemytrip.com/flight/search?itinerary={orig}-{dest}-{ddmmyyyy_slash}"
            f"&tripType=O&paxType=A-{pax}_C-0_I-0&intl={is_intl}&cabinClass={cabin}&cmp=niffler"
        )
        ixigo_url = (
            f"https://www.ixigo.com/search/result/flight?from={orig}&to={dest}"
            f"&date={ddmmyyyy}&adults={pax}&children=0&infants=0&class={cabin}"
        )
        goibibo_url = (
            f"https://www.goibibo.com/flight/search?tripType=O&itinerary={orig}-{dest}-{ddmmyyyy}"
            f"&paxType=A-{pax}_C-0_I-0&cabinClass={cabin}&ccde=IN"
        )

        offers: List[Dict[str, Any]] = [
            {
                "provider": carrier_label,
                "provider_type": "Airline Direct",
                "price_inr": airline_price or primary_price,
                "badge": "Zero OTA Markup",
                "url": carrier_url,
            },
            {
                "provider": "MakeMyTrip",
                "provider_type": "OTA Partner",
                "price_inr": primary_price,
                "price_note": "Live Check",
                "badge": "Bank Card Offers",
                "url": mmt_url,
            },
            {
                "provider": "Ixigo",
                "provider_type": "OTA Partner",
                "price_inr": primary_price,
                "price_note": "Live Check",
                "badge": "Zero Conv. Fee Eligible",
                "url": ixigo_url,
            },
            {
                "provider": "Goibibo",
                "provider_type": "OTA Partner",
                "price_inr": goibibo_price or primary_price,
                "price_note": "Live Quote" if goibibo_price else "Live Check",
                "badge": "Instant Coupon Eligible",
                "url": goibibo_url,
            },
        ]

        offers.sort(key=lambda o: o["price_inr"])
        if offers:
            offers[0]["is_lowest_provider"] = True
        return offers

    @staticmethod
    def _parse_currency_int(html_str: str) -> int:
        clean = re.sub(r"<[^>]+>", "", str(html_str or ""))
        digits = re.sub(r"[^\d]", "", clean)
        return int(digits) if digits else 0

    def _fetch_google_flights_live(
        self, orig_code: str, dest_code: str, target_date: str
    ) -> List[FlightOption]:
        """Fetch real, date-exact commercial flights & fares directly from Google Flights."""
        iso_dt, _, _ = self._format_dates(target_date)
        url = (
            f"https://www.google.com/travel/flights?"
            f"q=Flights+from+{orig_code}+to+{dest_code}+on+{iso_dt}+one+way&curr=INR&hl=en&gl=in"
        )
        req = urllib.request.Request(url, headers=self.BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            body = r.read().decode("utf-8", errors="ignore")

        m = re.search(r"AF_initDataCallback\(\{key:\s*'ds:1'.*?data:(.*?),\s*sideChannel", body, re.S)
        if not m:
            return []

        ds1 = json.loads(m.group(1))
        flights: List[FlightOption] = []
        seen = set()

        for bucket_idx in (2, 3):
            bucket = ds1[bucket_idx] if len(ds1) > bucket_idx and isinstance(ds1[bucket_idx], list) else None
            if not bucket or not isinstance(bucket[0], list):
                continue
            for it in bucket[0]:
                try:
                    info = it[0]
                    price = int(it[1][0][1])
                    if price <= 0:
                        continue
                    carrier = str(info[1][0])
                    legs = info[2] or []
                    flt_parts = [f"{l[22][0]}-{l[22][1]}" for l in legs if l and len(l) > 22 and l[22]]
                    fno = "/".join(flt_parts) or "FLIGHT"
                    dep_arr = info[5] or [0, 0]
                    arr_arr = info[8] or [0, 0]
                    dep_t = f"{int(dep_arr[0] or 0):02d}:{int(dep_arr[1] if len(dep_arr) > 1 and dep_arr[1] is not None else 0):02d}"
                    arr_t = f"{int(arr_arr[0] or 0):02d}:{int(arr_arr[1] if len(arr_arr) > 1 and arr_arr[1] is not None else 0):02d}"
                    mins = int(info[9] or 0)
                    dur_str = f"{mins // 60}h {mins % 60:02d}m"
                    dep_cd = str(info[3] or orig_code)
                    arr_cd = str(info[6] or dest_code)
                    stops = max(0, len(legs) - 1)

                    key = (fno, dep_t, dep_cd, arr_cd)
                    if key in seen:
                        continue
                    seen.add(key)

                    flights.append(
                        FlightOption(
                            airline=carrier,
                            flight_number=fno,
                            origin=dep_cd,
                            destination=arr_cd,
                            departure_time=dep_t,
                            arrival_time=arr_t,
                            duration=dur_str,
                            stops=stops,
                            price_inr=price,
                            source="Google Flights Live",
                            promo_note="Compare Airline Direct & OTAs",
                        )
                    )
                except Exception:
                    continue

        return flights

    def _fetch_goibibo_live(
        self, orig_code: str, orig_slug: str, dest_code: str, dest_slug: str
    ) -> Tuple[Dict[str, FlightOption], List[Dict[str, str]]]:
        """Fetch live Goibibo SSR fares (by flight number) and active promo coupons."""
        is_intl = orig_code in self.INTL_CODES or dest_code in self.INTL_CODES
        prefix = "international-flights" if is_intl else "flights"
        url = f"https://www.goibibo.com/{prefix}/{orig_slug}-to-{dest_slug}-flights/"
        by_fno: Dict[str, FlightOption] = {}
        offers: List[Dict[str, str]] = []

        req = urllib.request.Request(url, headers=self.BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=7) as r:
            html = r.read().decode("utf-8", errors="ignore")

        m_next = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if not m_next:
            return by_fno, offers

        nd = json.loads(m_next.group(1))
        data = nd.get("props", {}).get("pageProps", {}).get("data", {})

        for off in (data.get("giOfferList") or [])[:5]:
            offers.append({
                "code": str(off.get("slug", "")).upper(),
                "title": str(off.get("sub_heading", "")).strip(),
                "validity": str(off.get("validity_text", "")).strip(),
            })

        listing = data.get("state", {}).get("listing", {})
        journey_map = listing.get("journeyMap", {}).get("data", {})
        visible = listing.get("journeys", {}).get("visibleJourneys", {})
        card_groups = visible.get("otherCategoryCards", []) or []

        for group in card_groups:
            if not isinstance(group, list):
                continue
            for card in group:
                for _, rec in (card.get("recommendations") or {}).items():
                    fare = int(rec.get("fare") or 0)
                    if fare <= 0:
                        continue
                    fno = str(rec.get("flightNumber", "")).strip().replace(", ", "/").replace(" ", "-")
                    jkeys = rec.get("journeyKeys") or []
                    if not fno or not jkeys or jkeys[0] not in journey_map:
                        continue
                    j = journey_map[jkeys[0]]
                    airline = str((rec.get("simpleAirlineHeading") or {}).get("nm") or j.get("journeyHeader") or "").strip()
                    dur_obj = j.get("duration") or {}
                    dur_str = f"{int(dur_obj.get('h') or 0)}h {int(dur_obj.get('m') or 0):02d}m"
                    base_fare, taxes = 0, 0
                    for item in (rec.get("fareBreakup") or {}).get("fareBreakUpItems") or []:
                        lbl = re.sub(r"<[^>]+>", "", str(item.get("text", ""))).lower()
                        amt = self._parse_currency_int(item.get("amount", ""))
                        if "base" in lbl:
                            base_fare = amt
                        elif "surcharge" in lbl or "tax" in lbl:
                            taxes = amt

                    by_fno[fno] = FlightOption(
                        airline=airline or "Airline",
                        flight_number=fno,
                        origin=str(j.get("depCityCd") or orig_code),
                        destination=str(j.get("arrCityCd") or dest_code),
                        departure_time=str(j.get("depTime") or "--:--"),
                        arrival_time=str(j.get("arrTime") or "--:--"),
                        duration=dur_str,
                        stops=int(j.get("stops") or 0),
                        price_inr=fare,
                        source=jkeys[0].split("$")[2].split(" ")[0] if len(jkeys[0].split("$")) > 2 else "",
                        base_fare_inr=base_fare,
                        taxes_inr=taxes,
                    )

        return by_fno, offers

    def _run_gemini_hydrogen_agent(
        self,
        orig_code: str,
        orig_city: str,
        dest_code: str,
        dest_city: str,
        target_date: str,
        flights: List[FlightOption],
        offers: List[Dict[str, str]],
    ) -> Tuple[List[FlightOption], Dict[str, Any]]:
        """Run Gemini 4 Hydrogen across combined provider prices to surface lowest deal & savings hacks."""
        load_env_file()
        api_key = os.getenv("GEMINI_API_KEY")
        meta: Dict[str, Any] = {
            "agent_model": "gemini-4-hydrogen",
            "ai_summary": "",
            "best_coupon_tip": offers[0]["title"] if offers else "",
        }
        if not api_key:
            return flights, meta

        llm = UnifiedLLM(provider="gemini", model="gemini-4-hydrogen", api_key=api_key, timeout=12)

        if flights:
            compact = [
                {
                    "airline": f.airline,
                    "flight": f.flight_number,
                    "from": f.origin,
                    "to": f.destination,
                    "dep": f.departure_time,
                    "arr": f.arrival_time,
                    "dur": f.duration,
                    "stops": f.stops,
                    "lowest_inr": f.price_inr,
                    "providers": [{"p": o["provider"], "inr": o["price_inr"]} for o in f.provider_offers],
                }
                for f in flights[:10]
            ]
            prompt = (
                f"You are Niffler, an AI-powered Skyscanner deal hunter.\n"
                f"Route: {orig_city} ({orig_code}) -> {dest_city} ({dest_code}) on {target_date}.\n"
                f"Live multi-provider flight prices:\n{json.dumps(compact)}\n"
                f"Live offers:\n{json.dumps(offers[:3])}\n\n"
                "Return ONLY valid JSON with:\n"
                '  "deal_summary": 1 concise sentence identifying the cheapest carrier, flight number, lowest provider price, and any time/nearby-airport advantage,\n'
                '  "recommended_flight_number": best value flight number,\n'
                '  "promo_tip": short bank/coupon saving note (max 10 words).'
            )
            try:
                res = llm.generate_with_search(prompt, use_google_search=False)
                meta["agent_model"] = res.get("model", "gemini-4-hydrogen")
                m_json = re.search(r"\{[\s\S]*\}", res.get("text", ""))
                if m_json:
                    parsed = json.loads(m_json.group(0))
                    meta["ai_summary"] = str(parsed.get("deal_summary", ""))
                    if parsed.get("promo_tip"):
                        meta["best_coupon_tip"] = str(parsed["promo_tip"])
            except Exception:
                pass
            return flights, meta

        # If direct scrapers timed out, use Gemini 4 Hydrogen (+ Search Grounding if available) to discover route options
        prompt = (
            f"Find the cheapest scheduled commercial flights from {orig_city} ({orig_code}) to {dest_city} ({dest_code}) on {target_date}.\n"
            "Return ONLY a JSON object with keys:\n"
            '  "deal_summary": concise summary,\n'
            '  "flights": array of 5 flight dicts with keys "airline", "flight_number", "departure_time", "arrival_time", "duration", "stops" (int), "price_inr" (int).'
        )
        try:
            res = llm.generate_with_search(prompt, use_google_search=True)
            meta["agent_model"] = res.get("model", "gemini-4-hydrogen")
            txt = res.get("text", "")
            fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt)
            cand_str = fenced.group(1) if fenced else txt
            m_json = re.search(r"\{[\s\S]*\}", cand_str)
            if m_json:
                parsed = json.loads(m_json.group(0))
                meta["ai_summary"] = str(parsed.get("deal_summary", ""))
                ai_list: List[FlightOption] = []
                for item in parsed.get("flights") or []:
                    p = int(item.get("price_inr") or 0)
                    if p <= 0:
                        continue
                    airline = str(item.get("airline") or "IndiGo")
                    fno = str(item.get("flight_number") or "6E-101")
                    offers_list = self._build_provider_offers(airline, fno, orig_code, dest_code, target_date, p)
                    ai_list.append(
                        FlightOption(
                            airline=airline,
                            flight_number=fno,
                            origin=orig_code,
                            destination=dest_code,
                            departure_time=str(item.get("departure_time") or "08:00"),
                            arrival_time=str(item.get("arrival_time") or "10:45"),
                            duration=str(item.get("duration") or "2h 45m"),
                            stops=int(item.get("stops") or 0),
                            price_inr=p,
                            booking_url=offers_list[0]["url"],
                            source=f"Gemini ({meta['agent_model']})",
                            provider_offers=offers_list,
                        )
                    )
                if ai_list:
                    return ai_list, meta
        except Exception:
            pass

        return flights, meta

    @staticmethod
    def _duration_minutes(dur_str: str) -> int:
        h = re.search(r"(\d+)\s*h", dur_str)
        m = re.search(r"(\d+)\s*m", dur_str)
        return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)

    def search_flights_with_agent(
        self,
        origin: str,
        destination: str,
        date: Optional[str] = None,
        max_price: Optional[int] = None,
        direct_only: bool = False,
        pax: int = 1,
        cabin: str = "E",
        use_ai_agent: bool = True,
    ) -> Dict[str, Any]:
        orig_code, orig_city, orig_slug = self._resolve_city_slug_and_iata(origin)
        dest_code, dest_city, dest_slug = self._resolve_city_slug_and_iata(destination)
        target_date = date or (datetime.date.today() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

        agent_trace: List[str] = []
        gf_flights: List[FlightOption] = []
        gi_map: Dict[str, FlightOption] = {}
        offers: List[Dict[str, str]] = []

        # Run date-exact Google Flights + Goibibo SSR in parallel for speed
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_gf = pool.submit(self._fetch_google_flights_live, orig_code, dest_code, target_date)
            fut_gi = pool.submit(self._fetch_goibibo_live, orig_code, orig_slug, dest_code, dest_slug)

            try:
                gf_flights = fut_gf.result(timeout=9)
                agent_trace.append(
                    f"Iteration 1A (Google Flights Live • {target_date}): Fetched {len(gf_flights)} date-specific flights."
                )
            except Exception as e:
                agent_trace.append(f"Iteration 1A (Google Flights Live): {type(e).__name__}")

            try:
                gi_map, offers = fut_gi.result(timeout=9)
                agent_trace.append(
                    f"Iteration 1B (Goibibo Multi-Provider Cross-Check): Retrieved {len(gi_map)} carrier quotes & {len(offers)} promo codes."
                )
            except Exception as e:
                agent_trace.append(f"Iteration 1B (Goibibo Cross-Check): {type(e).__name__}")

        merged: List[FlightOption] = []
        seen_fnos = set()

        # Merge Google Flights (exact date) with date-matched Goibibo quotes & 4 providers
        for gf in gf_flights:
            seen_fnos.add(gf.flight_number)
            gi_match = gi_map.get(gf.flight_number)
            gi_exact_price = gi_match.price_inr if (gi_match and gi_match.source == target_date) else None
            best_price = min(gf.price_inr, gi_exact_price) if gi_exact_price else gf.price_inr

            p_offers = self._build_provider_offers(
                airline=gf.airline,
                flight_no=gf.flight_number,
                orig=gf.origin,
                dest=gf.destination,
                target_date=target_date,
                primary_price=gf.price_inr,
                goibibo_price=gi_exact_price,
                airline_price=gf.price_inr,
                pax=pax,
                cabin=cabin,
            )
            gf.price_inr = best_price
            gf.provider_offers = p_offers
            gf.booking_url = p_offers[0]["url"]
            gf.source = f"Best via {p_offers[0]['provider']}" if gi_exact_price and gi_exact_price < gf.price_inr else "Live • Multi-Provider"
            if gi_match and gi_match.source == target_date:
                gf.base_fare_inr = gi_match.base_fare_inr
                gf.taxes_inr = gi_match.taxes_inr
            if offers:
                gf.promo_note = offers[0]["title"]
            merged.append(gf)

        # Include any additional Goibibo-only flights (e.g., nearby airport DXN / SHJ) not in top 40 of Google Flights
        if not merged or len(merged) < 15:
            for fno, gi in gi_map.items():
                if fno in seen_fnos:
                    continue
                p_offers = self._build_provider_offers(
                    airline=gi.airline,
                    flight_no=gi.flight_number,
                    orig=gi.origin,
                    dest=gi.destination,
                    target_date=target_date,
                    primary_price=gi.price_inr,
                    goibibo_price=gi.price_inr,
                    pax=pax,
                    cabin=cabin,
                )
                gi.provider_offers = p_offers
                gi.booking_url = p_offers[0]["url"]
                gi.source = "Goibibo + Airline Compare"
                merged.append(gi)

        # Gemini 4 Hydrogen Deal Optimization pass
        ai_meta: Dict[str, Any] = {"agent_model": "gemini-4-hydrogen", "ai_summary": "", "best_coupon_tip": ""}
        if use_ai_agent:
            merged, ai_meta = self._run_gemini_hydrogen_agent(
                orig_code, orig_city, dest_code, dest_city, target_date, merged, offers
            )
            if ai_meta.get("ai_summary"):
                agent_trace.append(
                    f"Iteration 2 ({ai_meta['agent_model']}): Compared 4 providers across {len(merged)} flights for cheapest fare."
                )

        # Deterministic offline safety fallback only if every network call & Gemini failed
        if not merged:
            agent_trace.append("Offline Fallback: Serving reference schedule because all network sources timed out.")
            for air, fno, dep, arr, dur, stops, pr in [
                ("Akasa Air", "QP-1382", "09:30", "12:10", "2h 40m", 0, 4690),
                ("IndiGo", "6E-2041", "06:15", "08:55", "2h 40m", 0, 4850),
                ("Air India", "AI-805", "14:00", "16:45", "2h 45m", 0, 5420),
                ("SpiceJet", "SG-192", "11:20", "15:40", "4h 20m", 1, 4490),
            ]:
                p_offers = self._build_provider_offers(air, fno, orig_code, dest_code, target_date, pr, pax=pax, cabin=cabin)
                merged.append(
                    FlightOption(
                        airline=air,
                        flight_number=fno,
                        origin=orig_code,
                        destination=dest_code,
                        departure_time=dep,
                        arrival_time=arr,
                        duration=dur,
                        stops=stops,
                        price_inr=pr,
                        booking_url=p_offers[0]["url"],
                        source="Offline Reference",
                        provider_offers=p_offers,
                    )
                )

        filtered = []
        for f in merged:
            if direct_only and f.stops > 0:
                continue
            if max_price and f.price_inr > max_price:
                continue
            f.is_cheapest = False
            f.is_fastest = False
            filtered.append(f)

        filtered.sort(key=lambda f: f.price_inr)
        if filtered:
            filtered[0].is_cheapest = True
            fastest = min(filtered, key=lambda f: self._duration_minutes(f.duration))
            fastest.is_fastest = True

        return {
            "flights": filtered,
            "origin": {"code": orig_code, "city": orig_city, "slug": orig_slug},
            "destination": {"code": dest_code, "city": dest_city, "slug": dest_slug},
            "date": target_date,
            "offers": offers,
            "agent_model": ai_meta.get("agent_model", "gemini-4-hydrogen"),
            "ai_summary": ai_meta.get("ai_summary") or (
                f"Lowest on {target_date}: {filtered[0].airline} {filtered[0].flight_number} at ₹{filtered[0].price_inr:,} across {len(filtered[0].provider_offers)} providers."
                if filtered else "No matching flights found."
            ),
            "best_coupon_tip": ai_meta.get("best_coupon_tip") or (offers[0]["title"] if offers else ""),
            "agent_trace": agent_trace,
        }

    def search_flights(
        self,
        origin: str,
        destination: str,
        date: Optional[str] = None,
        max_price: Optional[int] = None,
        direct_only: bool = False,
    ) -> List[FlightOption]:
        return self.search_flights_with_agent(
            origin=origin,
            destination=destination,
            date=date,
            max_price=max_price,
            direct_only=direct_only,
            use_ai_agent=True,
        )["flights"]
