"""
Passenger auto-fill and direct payment gateway handoff coordinator.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import json
import uuid
import datetime
import urllib.parse
from ..config import UserProfile


@dataclass
class BookingSession:
    session_id: str
    booking_type: str  # 'flight', 'hotel', 'train', 'bus'
    item_title: str
    amount_inr: int
    taxes_inr: int
    convenience_fee_inr: int
    total_payable_inr: int
    passenger_name: str
    passenger_age: int
    passenger_gender: str
    contact_email: str
    contact_phone: str
    payment_gateway_url: str
    provider: str = "MakeMyTrip"
    provider_checkout_url: str = ""
    autofill_bookmarklet: str = ""
    status: str = "READY_FOR_PAYMENT"


class BookingHandoffEngine:
    """Auto-fills passenger manifests and generates multi-provider checkout handoffs."""

    def __init__(self, profile: Optional[UserProfile] = None):
        self.profile = profile or UserProfile()

    @staticmethod
    def build_autofill_bookmarklet(profile: UserProfile) -> str:
        """Build a bookmarklet JS URI that fills non-sensitive passenger fields on partner forms."""
        parts = (profile.full_name or "Guest Traveller").strip().split()
        first = parts[0] if parts else "Guest"
        last = " ".join(parts[1:]) if len(parts) > 1 else ""
        phone = "".join(c for c in (profile.phone or "") if c.isdigit())[-10:]
        payload = json.dumps({
            "full": profile.full_name,
            "first": first,
            "last": last,
            "email": profile.email,
            "phone": phone,
            "age": str(profile.age),
            "gender": profile.gender,
        })
        js = (
            f"javascript:(function(){{var d={payload};"
            "document.querySelectorAll('input').forEach(function(i){"
            "var k=(i.name+i.id+i.placeholder+(i.getAttribute('aria-label')||'')).toLowerCase();"
            "var v=null;"
            "if(/first.?name|fname|given/.test(k))v=d.first;"
            "else if(/last.?name|lname|surname/.test(k))v=d.last;"
            "else if(/full.?name|pax.?name|traveller/.test(k))v=d.full;"
            "else if(/mail/.test(k))v=d.email;"
            "else if(/phone|mobile|contact/.test(k))v=d.phone;"
            "else if(/age/.test(k))v=d.age;"
            "if(v!==null&&!i.disabled&&i.type!=='hidden'){"
            "var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
            "s.call(i,v);i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}));}"
            "});})();"
        )
        return js

    def prepare_flight_handoff(
        self,
        airline: str,
        flight_number: str,
        origin: str,
        destination: str,
        fare_inr: int,
        travel_date: Optional[str] = None,
        provider: str = "MakeMyTrip",
        provider_url: str = "",
    ) -> BookingSession:
        """Create a prepared flight booking session across the chosen provider."""
        sess_id = f"NF-FLT-{uuid.uuid4().hex[:8].upper()}"
        taxes = int(fare_inr * 0.12)
        conv_fee = 0 if "official" in provider.lower() else 350
        total = fare_inr + taxes + conv_fee

        params = {
            "session": sess_id,
            "type": "flight",
            "pax": self.profile.full_name,
            "email": self.profile.email,
            "phone": self.profile.phone,
            "flight": flight_number,
            "route": f"{origin}-{destination}",
            "date": travel_date or "",
            "amount": total,
        }
        payment_url = f"https://payment.makemytrip.com/checkout?{urllib.parse.urlencode(params)}"
        checkout_url = provider_url or f"https://www.makemytrip.com/flight/search?itinerary={origin}-{destination}-{(travel_date or '').replace('-', '/')}&tripType=O&paxType=A-1_C-0_I-0"

        return BookingSession(
            session_id=sess_id,
            booking_type="Flight",
            item_title=f"{airline} ({flight_number}) • {origin} → {destination}",
            amount_inr=fare_inr,
            taxes_inr=taxes,
            convenience_fee_inr=conv_fee,
            total_payable_inr=total,
            passenger_name=self.profile.full_name,
            passenger_age=self.profile.age,
            passenger_gender=self.profile.gender,
            contact_email=self.profile.email,
            contact_phone=self.profile.phone,
            payment_gateway_url=payment_url,
            provider=provider,
            provider_checkout_url=checkout_url,
            autofill_bookmarklet=self.build_autofill_bookmarklet(self.profile),
        )

    def prepare_hotel_handoff(
        self,
        hotel_name: str,
        city: str,
        nights: int,
        price_per_night: int,
        provider: str = "MakeMyTrip",
        provider_url: str = "",
    ) -> BookingSession:
        """Create a prepared hotel booking session landing on checkout."""
        sess_id = f"NF-HTL-{uuid.uuid4().hex[:8].upper()}"
        base_amt = price_per_night * nights
        taxes = int(base_amt * 0.18)
        total = base_amt + taxes

        params = {
            "session": sess_id,
            "type": "hotel",
            "guest": self.profile.full_name,
            "hotel": hotel_name,
            "city": city,
            "amount": total,
        }
        payment_url = f"https://payment.makemytrip.com/hotels/checkout?{urllib.parse.urlencode(params)}"
        checkout_url = provider_url or payment_url

        return BookingSession(
            session_id=sess_id,
            booking_type="Hotel",
            item_title=f"{hotel_name} ({city}) • {nights} Night(s)",
            amount_inr=base_amt,
            taxes_inr=taxes,
            convenience_fee_inr=0,
            total_payable_inr=total,
            passenger_name=self.profile.full_name,
            passenger_age=self.profile.age,
            passenger_gender=self.profile.gender,
            contact_email=self.profile.email,
            contact_phone=self.profile.phone,
            payment_gateway_url=payment_url,
            provider=provider,
            provider_checkout_url=checkout_url,
            autofill_bookmarklet=self.build_autofill_bookmarklet(self.profile),
        )
