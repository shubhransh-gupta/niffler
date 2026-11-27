// goNiffler — Goibibo-Style OTA Client + Live Web & Gemini 4 Hydrogen Agent Integration
document.addEventListener("DOMContentLoaded", () => {
  let currentSection = "travel";
  let currentTravelMode = "flights";
  let allFlights = [];
  let currentSort = "cheapest";

  // Set default departure date (+7 days)
  const dateInput = document.getElementById("travel-date");
  if (dateInput && !dateInput.value) {
    const dt = new Date(Date.now() + 7 * 86400 * 1000);
    dateInput.value = dt.toISOString().split("T")[0];
  }

  // Airline monogram color styling
  const CARRIER_COLORS = {
    "6E": "#0b4a9f",
    "AI": "#c8102e",
    "QP": "#ff6200",
    "SG": "#e11d48",
    "IX": "#ea580c",
    "IC": "#0284c7",
    "WY": "#0f766e",
    "UK": "#581c87",
  };

  function getCarrierBadge(airline, flightNo) {
    const code = (flightNo || "").split(/[-\s]/)[0].toUpperCase().slice(0, 2) || airline.slice(0, 2).toUpperCase();
    const bg = CARRIER_COLORS[code] || "#2276e3";
    return { code, bg };
  }

  // 1. Top Navbar Section & Mode Switching
  const navTabs = document.querySelectorAll(".go-nav-tab");
  const views = {
    travel: document.getElementById("view-travel"),
    itr: document.getElementById("view-itr"),
    epf: document.getElementById("view-epf"),
  };

  navTabs.forEach(btn => {
    btn.addEventListener("click", () => {
      navTabs.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const sec = btn.getAttribute("data-section");
      currentSection = sec;
      Object.values(views).forEach(v => v.classList.remove("active"));
      if (views[sec]) views[sec].classList.add("active");

      if (sec === "travel") {
        currentTravelMode = btn.getAttribute("data-mode") || "flights";
        updateTravelSearchUI();
        fetchTravelResults();
      }
    });
  });

  document.getElementById("brand-home").addEventListener("click", () => {
    navTabs[0].click();
  });

  // Trip type pill toggle
  document.querySelectorAll(".radio-pill input").forEach(inp => {
    inp.addEventListener("change", () => {
      document.querySelectorAll(".radio-pill").forEach(p => p.classList.remove("active"));
      inp.closest(".radio-pill").classList.add("active");
    });
  });

  // Special fare pills
  document.querySelectorAll(".sf-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".sf-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
    });
  });

  // Quick route chips
  document.querySelectorAll(".qr-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.getElementById("travel-origin").value = chip.getAttribute("data-orig");
      document.getElementById("travel-dest").value = chip.getAttribute("data-dest");
      if (currentTravelMode !== "flights") {
        navTabs[0].click();
      } else {
        fetchTravelResults();
      }
    });
  });

  // Swap button
  document.getElementById("btn-swap-route").addEventListener("click", () => {
    const orig = document.getElementById("travel-origin");
    const dest = document.getElementById("travel-dest");
    const subO = document.getElementById("sub-origin");
    const subD = document.getElementById("sub-dest");
    const tmp = orig.value;
    orig.value = dest.value;
    dest.value = tmp;
    const tmpS = subO.innerText;
    subO.innerText = subD.innerText;
    subD.innerText = tmpS;
  });

  // Agent trace drawer toggle
  document.getElementById("btn-toggle-trace").addEventListener("click", () => {
    const drawer = document.getElementById("agent-trace-drawer");
    drawer.style.display = drawer.style.display === "none" ? "block" : "none";
  });

  function updateTravelSearchUI() {
    const heroHeading = document.getElementById("hero-heading");
    const ctaBtn = document.getElementById("btn-search-travel");
    const sidebar = document.getElementById("ota-sidebar");
    const sortBar = document.getElementById("go-sort-bar");
    const insightBar = document.getElementById("deal-insight-bar");
    const orig = document.getElementById("travel-origin");
    const dest = document.getElementById("travel-dest");
    const subO = document.getElementById("sub-origin");
    const subD = document.getElementById("sub-dest");

    if (currentTravelMode === "flights") {
      heroHeading.innerText = "Domestic and International Flights";
      ctaBtn.innerText = "SEARCH FLIGHTS";
      sidebar.style.display = "block";
      sortBar.style.display = "grid";
      insightBar.style.display = "flex";
      if (!orig.value) orig.value = "DEL";
      if (!dest.value) dest.value = "BLR";
      subO.innerText = "Origin Airport / City";
      subD.innerText = "Destination Airport / City";
    } else if (currentTravelMode === "hotels") {
      heroHeading.innerText = "Book Hotels, Resorts & Homestays";
      ctaBtn.innerText = "SEARCH HOTELS";
      sidebar.style.display = "none";
      sortBar.style.display = "none";
      insightBar.style.display = "none";
      dest.value = "GOA";
      subO.innerText = "Guest City";
      subD.innerText = "Destination City";
    } else if (currentTravelMode === "trains") {
      heroHeading.innerText = "IRCTC Authorised Train Ticket Booking";
      ctaBtn.innerText = "SEARCH TRAINS";
      sidebar.style.display = "none";
      sortBar.style.display = "none";
      insightBar.style.display = "none";
      orig.value = "NDLS";
      dest.value = "MMCT";
      subO.innerText = "Origin Railway Station";
      subD.innerText = "Destination Railway Station";
    } else if (currentTravelMode === "buses") {
      heroHeading.innerText = "Online AC Sleeper & Volvo Bus Booking";
      ctaBtn.innerText = "SEARCH BUSES";
      sidebar.style.display = "none";
      sortBar.style.display = "none";
      insightBar.style.display = "none";
      orig.value = "BLR";
      dest.value = "HYD";
      subO.innerText = "Boarding City";
      subD.innerText = "Dropping City";
    }
  }

  // 2. Travel Search Action
  document.getElementById("btn-search-travel").addEventListener("click", fetchTravelResults);

  async function fetchTravelResults() {
    const origin = document.getElementById("travel-origin").value.trim() || "DEL";
    const dest = document.getElementById("travel-dest").value.trim() || "BLR";
    const dateVal = document.getElementById("travel-date").value;
    const directOnly = document.getElementById("chk-direct-top").checked;
    const container = document.getElementById("travel-cards");

    container.innerHTML = `
      <div class="go-card" style="padding:2.2rem; text-align:center; color:#6e7582;">
        <strong>Searching live fares across airlines &amp; Goibibo for ${origin.toUpperCase()} &rarr; ${dest.toUpperCase()}...</strong>
        <div style="font-size:0.8rem; margin-top:0.4rem;">Gemini 4 Hydrogen Deal Agent is iterating for the cheapest fares &amp; promo codes.</div>
      </div>
    `;

    try {
      if (currentTravelMode === "flights") {
        const params = new URLSearchParams({
          origin,
          destination: dest,
          with_meta: "true",
          direct: directOnly ? "true" : "false",
        });
        if (dateVal) params.set("date", dateVal);

        const res = await fetch(`/api/flights?${params.toString()}`);
        const payload = await res.json();

        allFlights = Array.isArray(payload) ? payload : (payload.flights || []);
        updateFlightMetadataUI(payload);
        populateDynamicAirlineFilters(allFlights);
        applyFiltersAndRenderFlights();
      } else if (currentTravelMode === "hotels") {
        const res = await fetch(`/api/hotels?city=${encodeURIComponent(dest)}`);
        const data = await res.json();
        renderHotels(data);
      } else if (currentTravelMode === "trains") {
        const res = await fetch(`/api/trains?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(dest)}`);
        const data = await res.json();
        renderTrains(data);
      } else if (currentTravelMode === "buses") {
        const res = await fetch(`/api/buses?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(dest)}`);
        const data = await res.json();
        renderBuses(data);
      }
    } catch (e) {
      container.innerHTML = `<div class="go-card" style="padding:1.5rem; color:#c8102e;">Unable to load live results: ${e.message}</div>`;
    }
  }

  function updateFlightMetadataUI(payload) {
    if (Array.isArray(payload)) return;

    if (payload.origin) {
      document.getElementById("sub-origin").innerText = `${payload.origin.city} (${payload.origin.code})`;
    }
    if (payload.destination) {
      document.getElementById("sub-dest").innerText = `${payload.destination.city} (${payload.destination.code})`;
    }

    document.getElementById("di-model-badge").innerText = `Live Web + ${payload.agent_model || "gemini-4-hydrogen"}`;
    document.getElementById("di-summary-text").innerText = payload.ai_summary || `${allFlights.length} live flights fetched.`;

    const couponBadge = document.getElementById("di-coupon-badge");
    if (payload.best_coupon_tip) {
      couponBadge.innerText = payload.best_coupon_tip;
      couponBadge.style.display = "inline-block";
    } else {
      couponBadge.style.display = "none";
    }

    const traceList = document.getElementById("agent-trace-list");
    traceList.innerHTML = (payload.agent_trace || []).map(step => `<li>${step}</li>`).join("");

    // Stop counts
    const nonStopCount = allFlights.filter(f => f.stops === 0).length;
    const oneStopCount = allFlights.filter(f => f.stops > 0).length;
    document.getElementById("cnt-stop-0").innerText = nonStopCount;
    document.getElementById("cnt-stop-1").innerText = oneStopCount;

    // Price slider bounds
    if (allFlights.length > 0) {
      const prices = allFlights.map(f => f.price_inr);
      const minP = Math.min(...prices);
      const maxP = Math.max(...prices);
      const slider = document.getElementById("range-max-price");
      slider.min = minP;
      slider.max = Math.max(maxP, minP + 500);
      slider.value = slider.max;
      document.getElementById("min-price-bound").innerText = `₹${minP.toLocaleString()}`;
      document.getElementById("max-price-bound").innerText = `₹${maxP.toLocaleString()}`;
      document.getElementById("lbl-price-cap").innerText = "All Fares";

      document.getElementById("sort-sub-cheapest").innerText = `Starting ₹${minP.toLocaleString()}`;
      const fastestFlight = [...allFlights].sort((a, b) => durToMins(a.duration) - durToMins(b.duration))[0];
      document.getElementById("sort-sub-fastest").innerText = `${fastestFlight.duration} • ₹${fastestFlight.price_inr.toLocaleString()}`;
      document.getElementById("sort-sub-count").innerText = `${allFlights.length} flights found`;
    }
  }

  function populateDynamicAirlineFilters(flights) {
    const list = document.getElementById("airlines-filter-list");
    const airlineMap = {};
    flights.forEach(f => {
      if (!airlineMap[f.airline] || f.price_inr < airlineMap[f.airline]) {
        airlineMap[f.airline] = f.price_inr;
      }
    });
    list.innerHTML = Object.entries(airlineMap)
      .sort((a, b) => a[1] - b[1])
      .map(([name, minPrice]) => `
        <label class="chk-row">
          <input type="checkbox" class="filter-airline" value="${name}" checked>
          <span>${name}</span>
          <span class="chk-count">₹${minPrice.toLocaleString()}</span>
        </label>
      `).join("");

    document.querySelectorAll(".filter-airline").forEach(cb => {
      cb.addEventListener("change", applyFiltersAndRenderFlights);
    });
  }

  function durToMins(durStr) {
    const h = /(\d+)\s*h/.exec(durStr || "");
    const m = /(\d+)\s*m/.exec(durStr || "");
    return (h ? parseInt(h[1]) * 60 : 0) + (m ? parseInt(m[1]) : 0);
  }

  function timeToMins(tStr) {
    const parts = (tStr || "00:00").split(":");
    return (parseInt(parts[0]) || 0) * 60 + (parseInt(parts[1]) || 0);
  }

  function matchesTimeSlot(depTime, slot) {
    const mins = timeToMins(depTime);
    if (slot === "before6") return mins < 360;
    if (slot === "6to12") return mins >= 360 && mins < 720;
    if (slot === "12to18") return mins >= 720 && mins < 1080;
    if (slot === "after18") return mins >= 1080;
    return true;
  }

  function applyFiltersAndRenderFlights() {
    const checkedStops = [...document.querySelectorAll(".filter-stop:checked")].map(c => parseInt(c.value));
    const maxPrice = parseInt(document.getElementById("range-max-price").value) || 999999;
    const activeAirlines = [...document.querySelectorAll(".filter-airline:checked")].map(c => c.value);
    const activeSlots = [...document.querySelectorAll(".time-slot-btn.active")].map(b => b.getAttribute("data-slot"));

    let list = allFlights.filter(f => {
      if (checkedStops.length > 0) {
        const sBucket = f.stops === 0 ? 0 : 1;
        if (!checkedStops.includes(sBucket)) return false;
      }
      if (f.price_inr > maxPrice) return false;
      if (activeAirlines.length > 0 && !activeAirlines.includes(f.airline)) return false;
      if (activeSlots.length > 0 && !activeSlots.some(s => matchesTimeSlot(f.departure_time, s))) return false;
      return true;
    });

    if (currentSort === "cheapest") {
      list.sort((a, b) => a.price_inr - b.price_inr);
    } else if (currentSort === "fastest") {
      list.sort((a, b) => durToMins(a.duration) - durToMins(b.duration));
    } else if (currentSort === "early") {
      list.sort((a, b) => timeToMins(a.departure_time) - timeToMins(b.departure_time));
    } else if (currentSort === "value") {
      list.sort((a, b) => (a.price_inr + durToMins(a.duration) * 8) - (b.price_inr + durToMins(b.duration) * 8));
    }

    renderFlights(list);
  }

  // Filter & Sort Event Listeners
  document.querySelectorAll(".filter-stop").forEach(cb => cb.addEventListener("change", applyFiltersAndRenderFlights));
  document.getElementById("range-max-price").addEventListener("input", e => {
    const val = parseInt(e.target.value);
    document.getElementById("lbl-price-cap").innerText = `Up to ₹${val.toLocaleString()}`;
    applyFiltersAndRenderFlights();
  });
  document.querySelectorAll(".time-slot-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      btn.classList.toggle("active");
      applyFiltersAndRenderFlights();
    });
  });
  document.querySelectorAll(".sort-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".sort-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentSort = tab.getAttribute("data-sort");
      applyFiltersAndRenderFlights();
    });
  });
  document.getElementById("btn-reset-filters").addEventListener("click", () => {
    document.querySelectorAll(".filter-stop").forEach(c => (c.checked = false));
    document.querySelectorAll(".filter-airline").forEach(c => (c.checked = true));
    document.querySelectorAll(".time-slot-btn").forEach(b => b.classList.remove("active"));
    const slider = document.getElementById("range-max-price");
    slider.value = slider.max;
    document.getElementById("lbl-price-cap").innerText = "All Fares";
    applyFiltersAndRenderFlights();
  });

  function renderFlights(flights) {
    const container = document.getElementById("travel-cards");
    if (!flights || flights.length === 0) {
      container.innerHTML = `<div class="go-card" style="padding:2rem; text-align:center; color:#6e7582;">No flights match the current filters. Try clicking <strong>RESET ALL</strong>.</div>`;
      return;
    }

    container.innerHTML = "";
    flights.forEach(f => {
      const badge = getCarrierBadge(f.airline, f.flight_number);
      const stopsLabel = f.stops === 0 ? "Non stop" : `${f.stops} stop`;
      const stopsClass = f.stops === 0 ? "nonstop" : "withstop";

      const card = document.createElement("div");
      card.className = "go-card";
      card.innerHTML = `
        <div class="go-card-main">
          <div class="carrier-col">
            <div class="carrier-badge" style="background:${badge.bg};">${badge.code}</div>
            <div>
              <div class="carrier-name">${f.airline}</div>
              <div class="carrier-fno">${f.flight_number}</div>
            </div>
          </div>

          <div class="timeline-col">
            <div class="time-point">
              <div class="tp-time">${f.departure_time}</div>
              <div class="tp-code">${f.origin}</div>
            </div>
            <div class="duration-line">
              <div class="dur-txt">${f.duration}</div>
              <div class="line-bar"></div>
              <div class="stops-txt ${stopsClass}">${stopsLabel}</div>
            </div>
            <div class="time-point">
              <div class="tp-time">${f.arrival_time}</div>
              <div class="tp-code">${f.destination}</div>
            </div>
          </div>

          <div class="price-col">
            <div class="price-wrap">
              <div class="p-amt">&#8377;${f.price_inr.toLocaleString()}</div>
              <div class="p-sub">per adult</div>
            </div>
            <button type="button" class="btn-go-book btn-book-flight">BOOK</button>
          </div>
        </div>
        <div class="go-card-footer">
          <div class="footer-left">
            ${f.is_cheapest ? '<span class="cheapest-flag">CHEAPEST FARE</span>' : ''}
            <span class="promo-pill">${f.promo_note || 'Use code GIUNIQUE for instant bank discount'}</span>
            <span>Cabin: ${f.cabin_baggage || '7 kg'} &bull; Check-in: ${f.checkin_baggage || '15 kg'}</span>
          </div>
          <span class="source-flag">${f.source || 'Goibibo Live'}</span>
        </div>
      `;
      card.querySelector(".btn-book-flight").addEventListener("click", () => openPaymentModal("flight", f));
      container.appendChild(card);
    });
  }

  function renderHotels(hotels) {
    const container = document.getElementById("travel-cards");
    container.innerHTML = "";
    hotels.forEach(h => {
      const card = document.createElement("div");
      card.className = "go-card";
      card.innerHTML = `
        <div class="generic-card-main">
          <div>
            <div class="gc-title">${h.name} &bull; ${h.property_type}</div>
            <div class="gc-sub">${h.location}, ${h.city} &bull; &#9733; ${h.user_rating}/5.0 (${h.reviews_count.toLocaleString()} reviews)</div>
            <div class="gc-tags">
              ${h.couple_friendly ? '<span class="gc-tag green">Couple Friendly</span>' : ''}
              ${h.free_cancellation ? '<span class="gc-tag">Free Cancellation</span>' : ''}
              ${(h.amenities || []).slice(0, 3).map(a => `<span class="gc-tag">${a}</span>`).join("")}
            </div>
          </div>
          <div class="price-col">
            <div class="price-wrap">
              <div class="p-amt">&#8377;${h.price_per_night_inr.toLocaleString()}</div>
              <div class="p-sub">per night + taxes</div>
            </div>
            <button type="button" class="btn-go-book btn-book-hotel">SELECT ROOM</button>
          </div>
        </div>
      `;
      card.querySelector(".btn-book-hotel").addEventListener("click", () => openPaymentModal("hotel", h));
      container.appendChild(card);
    });
  }

  function renderTrains(trains) {
    const container = document.getElementById("travel-cards");
    container.innerHTML = "";
    trains.forEach(t => {
      const classesHtml = Object.entries(t.classes_available)
        .map(([k, v]) => `<span class="gc-tag ${v.includes('AVAILABLE') ? 'green' : ''}"><strong>${k}</strong>: ${v} (₹${(t.base_fare_inr[k] || 950).toLocaleString()})</span>`)
        .join("");
      const card = document.createElement("div");
      card.className = "go-card";
      card.innerHTML = `
        <div class="generic-card-main">
          <div>
            <div class="gc-title">${t.train_number} &bull; ${t.train_name}</div>
            <div class="gc-sub">${t.origin_station} (${t.departure_time}) &rarr; ${t.destination_station} (${t.arrival_time}) &bull; ${t.travel_time}</div>
            <div class="gc-tags">${classesHtml}</div>
          </div>
          <div class="price-col">
            <a href="https://www.goibibo.com/trains/" target="_blank" class="btn-go-book">IRCTC BOOK</a>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  }

  function renderBuses(buses) {
    const container = document.getElementById("travel-cards");
    container.innerHTML = "";
    buses.forEach(b => {
      const card = document.createElement("div");
      card.className = "go-card";
      card.innerHTML = `
        <div class="generic-card-main">
          <div>
            <div class="gc-title">${b.operator} &bull; ${b.bus_type}</div>
            <div class="gc-sub">${b.origin} (${b.departure_time}) &rarr; ${b.destination} (${b.arrival_time}) &bull; ${b.duration} &bull; ${b.boarding_point}</div>
            <div class="gc-tags">
              <span class="gc-tag green">&#9733; ${b.rating}</span>
              <span class="gc-tag">${b.seats_left} seats left</span>
            </div>
          </div>
          <div class="price-col">
            <div class="price-wrap">
              <div class="p-amt">&#8377;${b.price_inr.toLocaleString()}</div>
              <div class="p-sub">per seat</div>
            </div>
            <a href="${b.booking_url}" target="_blank" class="btn-go-book">SELECT SEAT</a>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  }

  // 3. Booking Handoff Modal
  async function openPaymentModal(type, item) {
    const payload = type === "hotel"
      ? { type: "hotel", hotel_name: item.name, city: item.city, nights: 1, price: item.price_per_night_inr }
      : { type: "flight", airline: item.airline, flight_number: item.flight_number, origin: item.origin, destination: item.destination, fare: item.price_inr };

    try {
      const res = await fetch("/api/booking/handoff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const sess = await res.json();

      document.getElementById("modal-item-title").innerHTML = sess.item_title;
      document.getElementById("m-pax-name").innerText = sess.passenger_name;
      document.getElementById("m-pax-age").innerText = sess.passenger_age;
      document.getElementById("m-pax-gender").innerText = sess.passenger_gender;
      document.getElementById("m-pax-email").innerText = sess.contact_email;
      document.getElementById("m-pax-phone").innerText = sess.contact_phone;
      document.getElementById("m-sess-id").innerText = sess.session_id;

      // Use real Goibibo base/taxes breakup if present
      const baseFare = item.base_fare_inr > 0 ? item.base_fare_inr : sess.amount_inr;
      const taxesAmt = item.taxes_inr > 0 ? item.taxes_inr : sess.taxes_inr;
      document.getElementById("m-base-fare").innerText = `₹${baseFare.toLocaleString()}`;
      document.getElementById("m-taxes").innerText = `₹${taxesAmt.toLocaleString()}`;
      document.getElementById("m-conv-fee").innerText = `₹${sess.convenience_fee_inr.toLocaleString()}`;
      document.getElementById("m-total-amt").innerText = `₹${(item.base_fare_inr > 0 ? item.price_inr + sess.convenience_fee_inr : sess.total_payable_inr).toLocaleString()}`;

      document.getElementById("btn-goto-goibibo").href = item.booking_url || "https://www.goibibo.com/flights/";
      document.getElementById("btn-goto-payment").href = sess.payment_gateway_url;

      document.getElementById("booking-modal").classList.add("open");
    } catch (e) {
      alert("Booking handoff error: " + e.message);
    }
  }

  document.getElementById("btn-close-modal").addEventListener("click", () => {
    document.getElementById("booking-modal").classList.remove("open");
  });

  // 4. ITR Optimizer
  let lastITRJson = null;
  document.getElementById("btn-calc-itr").addEventListener("click", async () => {
    const salary = parseInt(document.getElementById("itr-salary").value) || 0;
    const tds = parseInt(document.getElementById("itr-tds").value) || 0;
    const sec80c = parseInt(document.getElementById("itr-80c").value) || 0;
    const sec80d = parseInt(document.getElementById("itr-80d").value) || 0;
    const hra = parseInt(document.getElementById("itr-hra").value) || 0;
    const pan = document.getElementById("itr-pan").value.trim();

    try {
      const res = await fetch("/api/itr/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          gross_salary: salary,
          tds,
          sec_80c: sec80c,
          sec_80d: sec80d,
          hra,
          pan,
          name: "Shubhransh Gupta",
        }),
      });
      const data = await res.json();
      lastITRJson = data.itr_1_json;

      document.getElementById("itr-results").style.display = "block";
      const isNew = data.recommended_regime === "NEW_REGIME";
      document.getElementById("showdown-banner").innerHTML = `🏆 Recommended: <strong>${isNew ? "New Tax Regime" : "Old Tax Regime"}</strong> &bull; You save <strong>₹${data.tax_savings_inr.toLocaleString()}</strong> in tax!`;

      document.getElementById("stat-new-tax").innerText = `₹${data.new_regime.total_tax_payable.toLocaleString()}`;
      document.getElementById("stat-new-deductions").innerText = `Std Deduction: ₹${data.new_regime.exemptions_and_deductions.toLocaleString()} | Taxable: ₹${data.new_regime.net_taxable_income.toLocaleString()}`;
      document.getElementById("stat-old-tax").innerText = `₹${data.old_regime.total_tax_payable.toLocaleString()}`;
      document.getElementById("stat-old-deductions").innerText = `Total Deductions: ₹${data.old_regime.exemptions_and_deductions.toLocaleString()} | Taxable: ₹${data.old_regime.net_taxable_income.toLocaleString()}`;

      document.getElementById("box-new-regime").className = isNew ? "regime-card winner" : "regime-card";
      document.getElementById("box-old-regime").className = !isNew ? "regime-card winner" : "regime-card";
    } catch (e) {
      alert("ITR calculation error: " + e.message);
    }
  });

  document.getElementById("btn-download-itr").addEventListener("click", () => {
    if (!lastITRJson) return;
    const blob = new Blob([JSON.stringify(lastITRJson, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ITR1_Sahaj_2024_25.json";
    a.click();
    URL.revokeObjectURL(url);
  });

  // 5. EPF Explorer
  document.getElementById("btn-explore-epf").addEventListener("click", async () => {
    const basic = parseInt(document.getElementById("epf-basic").value) || 50000;
    const tenure = parseFloat(document.getElementById("epf-tenure").value) || 4.0;
    const balance = parseInt(document.getElementById("epf-balance").value) || 350000;

    try {
      const res = await fetch(`/api/epf?basic=${basic}&tenure=${tenure}&balance=${balance}`);
      const data = await res.json();

      document.getElementById("epf-results").style.display = "block";
      document.getElementById("val-emp-share").innerText = `₹${data.summary.employee_share_balance_inr.toLocaleString()}`;
      document.getElementById("val-empr-share").innerText = `₹${data.summary.employer_share_balance_inr.toLocaleString()}`;
      document.getElementById("val-eps-share").innerText = `₹${data.summary.pension_scheme_balance_inr.toLocaleString()}`;
      document.getElementById("val-total-epf").innerText = `₹${data.summary.total_epf_balance_inr.toLocaleString()}`;

      document.getElementById("epf-rules-list").innerHTML = `
        <li><strong>Form 31 (Medical):</strong> ${data.eligibility.form_31_medical.rule}</li>
        <li><strong>Form 31 (Housing):</strong> ${data.eligibility.form_31_housing.eligible ? "✅ ELIGIBLE — " : "❌ NOT ELIGIBLE — "}${data.eligibility.form_31_housing.rule}</li>
        <li><strong>Form 31 (Marriage):</strong> ${data.eligibility.form_31_marriage.eligible ? "✅ ELIGIBLE — " : "❌ NOT ELIGIBLE — "}${data.eligibility.form_31_marriage.rule}</li>
        <li><strong>Form 19 (Full Settlement):</strong> ${data.eligibility.form_19_full_settlement.rule}</li>
        <li><strong>Form 10C (Pension):</strong> ${data.eligibility.form_10c_pension.rule}</li>
      `;
      document.getElementById("val-corpus").innerText = `₹${data.projection.projected_corpus_at_58_inr.toLocaleString()}`;
    } catch (e) {
      alert("EPF fetch error: " + e.message);
    }
  });

  // Initial load of live flights
  fetchTravelResults();
});
