"""
Unit tests for Niffler autonomous travel and citizen FinTech engine.
"""

import pytest
from niffler.travel.flights import FlightRadar
from niffler.travel.hotels import HotelRadar
from niffler.travel.trains import IRCTCRadar
from niffler.travel.buses import BusRadar
from niffler.travel.booking_handoff import BookingHandoffEngine
from niffler.citizen.itr_optimizer import ITROptimizer
from niffler.citizen.epf_explorer import EPFExplorer
from niffler.config import UserProfile, NifflerConfig, BharatConfig


def test_flight_radar_cheapest_tag():
    radar = FlightRadar()
    flights = radar.search_flights("DEL", "BLR")
    assert len(flights) > 0
    # Must have exactly one flagged as cheapest
    cheapest = [f for f in flights if f.is_cheapest]
    assert len(cheapest) == 1
    assert cheapest[0].price_inr == min(f.price_inr for f in flights)


def test_flight_radar_direct_filter():
    radar = FlightRadar()
    direct_flights = radar.search_flights("DEL", "BLR", direct_only=True)
    assert all(f.stops == 0 for f in direct_flights)


def test_hotel_radar_budget_filter():
    radar = HotelRadar()
    hotels = radar.search_hotels("GOA", max_budget=5000)
    assert all(h.price_per_night_inr <= 5000 for h in hotels)


def test_hotel_radar_couple_filter():
    radar = HotelRadar()
    hotels = radar.search_hotels("BENGALURU", couple_friendly_only=True)
    assert all(h.couple_friendly for h in hotels)


def test_irctc_train_search_and_tatkal():
    radar = IRCTCRadar()
    trains = radar.search_trains("NDLS", "MMCT")
    assert len(trains) > 0
    advisory = radar.get_tatkal_advisory()
    assert "10:00 AM" in advisory["ac_tatkal_opens"]
    assert "11:00 AM" in advisory["non_ac_tatkal_opens"]


def test_irctc_pnr_status():
    radar = IRCTCRadar()
    pnr = radar.check_pnr_status("2418901234")
    assert pnr.confirmation_probability > 0
    assert pnr.pnr == "2418901234"


def test_bus_radar():
    radar = BusRadar()
    buses = radar.search_buses("BLR", "HYD")
    assert len(buses) > 0
    assert buses[0].price_inr <= buses[-1].price_inr


def test_booking_handoff_engine():
    profile = UserProfile(full_name="Shubhransh Gupta", age=28, phone="+91 99999 88888")
    engine = BookingHandoffEngine(profile)
    sess = engine.prepare_flight_handoff("IndiGo", "6E-2041", "DEL", "BLR", 4500)

    assert sess.passenger_name == "Shubhransh Gupta"
    assert sess.amount_inr == 4500
    assert sess.taxes_inr == int(4500 * 0.12)
    assert sess.total_payable_inr > 4500
    assert "payment.makemytrip.com" in sess.payment_gateway_url


def test_itr_optimizer_rebate_and_slabs():
    optimizer = ITROptimizer()
    # Salary of 7.5 Lakh in New Regime has 75k std deduction -> taxable 6.75 Lakh -> 87A rebate gives zero tax!
    res = optimizer.optimize_and_generate_itr(
        pan="ABCDE1234F",
        name="Shubhransh Gupta",
        gross_salary=750000,
        tds_deducted=15000
    )
    assert res.new_regime.total_tax_payable == 0
    assert res.recommended_regime == "NEW_REGIME"
    assert "ITR" in res.itr_1_json


def test_itr_optimizer_high_bracket():
    optimizer = ITROptimizer()
    res = optimizer.optimize_and_generate_itr(
        pan="ABCDE1234F",
        name="Shubhransh Gupta",
        gross_salary=2000000,
        sec_80c=150000,
        sec_80d=25000,
        hra_exemption=180000,
        tds_deducted=250000
    )
    assert res.tax_savings_inr >= 0
    assert res.old_regime.gross_salary == 2000000
    assert res.new_regime.gross_salary == 2000000


def test_epf_explorer_contributions():
    explorer = EPFExplorer()
    summary = explorer.parse_or_simulate_account(
        uan="101234567890",
        monthly_basic_da=50000,
        years_of_service=4.0,
        starting_epf_balance=250000
    )
    assert summary.employee_share_balance_inr > 250000
    assert summary.employer_share_balance_inr > 0
    assert summary.pension_scheme_balance_inr > 0
    assert summary.current_interest_rate_pct == 8.25


def test_epf_withdrawal_rules():
    explorer = EPFExplorer()
    # Junior (2 years)
    rules_jr = explorer.check_withdrawal_eligibility(years_of_service=2.0, employee_balance=100000)
    assert rules_jr.form_31_medical["eligible"] is True
    assert rules_jr.form_31_housing["eligible"] is False

    # Senior (6 years)
    rules_sr = explorer.check_withdrawal_eligibility(years_of_service=6.0, employee_balance=500000)
    assert rules_sr.form_31_housing["eligible"] is True
    assert rules_sr.form_31_marriage["eligible"] is False


def test_epf_retirement_projection():
    explorer = EPFExplorer()
    proj = explorer.project_retirement_corpus(
        current_age=28,
        current_balance=300000,
        monthly_basic_da=50000,
        annual_increment_pct=5.0,
        retirement_age=58
    )
    assert proj.years_to_grow == 30
    assert proj.projected_corpus_at_58_inr > 10000000  # Will be > 1 Crore with compounding


def test_hotel_radar_destination_fallbacks():
    radar = HotelRadar()
    delhi_hotels = radar.search_hotels("Delhi")
    assert len(delhi_hotels) > 0
    assert any("delhi" in h.city.lower() or "delhi" in h.location.lower() for h in delhi_hotels)
    assert not any("calangute" in h.location.lower() for h in delhi_hotels)

    jaipur_hotels = radar.search_hotels("Jaipur")
    assert len(jaipur_hotels) > 0
    assert any("jaipur" in h.city.lower() or "jaipur" in h.location.lower() for h in jaipur_hotels)


def test_niffler_agent():
    from niffler.agent import NifflerAgent
    agent = NifflerAgent()
    resp_flt = agent.process_query("Find me cheapest flights from Delhi to Mumbai")
    assert "reply" in resp_flt
    assert resp_flt.get("action", {}).get("type") in ["SEARCH_FLIGHTS", "NONE"]

    resp_tax = agent.process_query("How much tax can I save on 15 lakh salary?")
    assert "reply" in resp_tax
    assert resp_tax.get("action", {}).get("type") in ["CALC_ITR", "NONE"]
