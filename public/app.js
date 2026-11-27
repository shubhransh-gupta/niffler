// Niffler — Smooth OTA Client with Calendar Picker, Guest Mode / Mobile OTP Auth, and Live Flight Agent
document.addEventListener("DOMContentLoaded", () => {
  let currentSection = "travel";
  let currentTravelMode = "flights";
  let allFlights = [];
  let currentSort = "cheapest";
  let loggedInUser = loadStoredUser();
  let otpSessionToken = "";
  let otpTargetPhone = "";
  let otpTargetName = "";

  // =========================================================================
  // 1. Date Picker Initialization + Click Anywhere on Box Opens Calendar
  // =========================================================================
  const depInput = document.getElementById("travel-date");
  const retInput = document.getElementById("return-date");

  function formatPrettyDate(isoDate) {
    if (!isoDate) return { main: "Select Date", sub: "Tap to open calendar" };
    const dt = new Date(isoDate + "T00:00:00");
    if (isNaN(dt.getTime())) return { main: isoDate, sub: "" };
    const day = String(dt.getDate()).padStart(2, "0");
    const month = dt.toLocaleString("en-IN", { month: "short" });
    const yr = String(dt.getFullYear()).slice(-2);
    const weekday = dt.toLocaleString("en-IN", { weekday: "long" });
    return { main: `${day} ${month} '${yr}`, sub: `${weekday} • Tap to change` };
  }

  function syncDateDisplays() {
    const depFmt = formatPrettyDate(depInput.value);
    document.getElementById("dep-date-pretty").innerText = depFmt.main;
    document.getElementById("dep-day-pretty").innerText = depFmt.sub;

    const retFmt = formatPrettyDate(retInput.value);
    document.getElementById("ret-date-pretty").innerText = retFmt.main;
    document.getElementById("ret-day-pretty").innerText = retFmt.sub;
  }

  const todayIso = new Date().toISOString().split("T")[0];
  const defaultDep = new Date(Date.now() + 7 * 86400 * 1000).toISOString().split("T")[0];
  const defaultRet = new Date(Date.now() + 10 * 86400 * 1000).toISOString().split("T")[0];
  depInput.min = todayIso;
  depInput.value = defaultDep;
  retInput.min = defaultDep;
  retInput.value = defaultRet;
  syncDateDisplays();

  depInput.addEventListener("change", () => {
    if (retInput.value && retInput.value < depInput.value) {
      retInput.value = depInput.value;
    }
    retInput.min = depInput.value;
    syncDateDisplays();
  });
  retInput.addEventListener("change", syncDateDisplays);

  function bindCalendarBox(boxId, inputEl) {
    const box = document.getElementById(boxId);
    if (!box || !inputEl) return;
    const triggerPicker = (e) => {
      e.preventDefault();
      if (typeof inputEl.showPicker === "function") {
        try {
          inputEl.showPicker();
          return;
        } catch (_) {}
      }
      inputEl.focus();
      inputEl.click();
    };
    box.addEventListener("click", triggerPicker);
    inputEl.addEventListener("click", (e) => {
      e.stopPropagation();
      if (typeof inputEl.showPicker === "function") {
        try {
          inputEl.showPicker();
        } catch (_) {}
      }
    });
  }

  bindCalendarBox("box-departure", depInput);
  bindCalendarBox("box-return", retInput);

  // =========================================================================
  // 2. Guest Mode & Mobile OTP Auth
  // =========================================================================
  function loadStoredUser() {
    try {
      const raw = localStorage.getItem("niffler_user");
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function renderAuthNavbar() {
    const area = document.getElementById("nav-auth-area");
    const heroChip = document.getElementById("guest-status-badge");
    if (loggedInUser && loggedInUser.phone) {
      const initials = (loggedInUser.name || "U")
        .split(" ")
        .map(w => w[0])
        .join("")
        .toUpperCase()
        .slice(0, 2);
      area.innerHTML = `
        <div class="user-signed-pill">
          <span class="user-avatar">${initials}</span>
          <div class="user-meta">
            <span class="user-hi">${loggedInUser.name}</span>
            <span class="user-sub">${loggedInUser.phone}</span>
          </div>
          <button type="button" class="btn-logout-mini" id="btn-logout">Sign out</button>
        </div>
      `;
      if (heroChip) heroChip.innerText = `Signed in: ${loggedInUser.phone}`;
      document.getElementById("btn-logout").addEventListener("click", () => {
        loggedInUser = null;
        localStorage.removeItem("niffler_user");
        renderAuthNavbar();
      });
    } else {
      area.innerHTML = `
        <button type="button" class="btn-login-otp" id="btn-open-login">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="20" x="5" y="2" rx="2" ry="2"/><path d="M12 18h.01"/></svg>
          <span>Login / OTP</span>
        </button>
      `;
      if (heroChip) heroChip.innerText = "Guest Access Enabled";
      document.getElementById("btn-open-login").addEventListener("click", openLoginModal);
    }
  }

  const loginModal = document.getElementById("login-modal");
  function openLoginModal() {
    document.getElementById("otp-step-1").style.display = "block";
    document.getElementById("otp-step-2").style.display = "none";
    document.getElementById("login-otp-code").value = "";
    loginModal.classList.add("open");
  }

  document.getElementById("btn-close-login").addEventListener("click", () => {
    loginModal.classList.remove("open");
  });

  document.getElementById("btn-back-otp").addEventListener("click", () => {
    document.getElementById("otp-step-1").style.display = "block";
    document.getElementById("otp-step-2").style.display = "none";
  });

  document.getElementById("btn-send-otp").addEventListener("click", async () => {
    const phone = document.getElementById("login-phone").value.replace(/\D/g, "").slice(-10);
    const name = document.getElementById("login-name").value.trim();
    if (phone.length !== 10) {
      alert("Please enter a valid 10-digit mobile number.");
      return;
    }

    try {
      const res = await fetch("/api/auth/send-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, name }),
      });
      const data = await res.json();
      if (!data.sent) {
        alert(data.error || "Could not send OTP.");
        return;
      }
      otpSessionToken = data.otp_token;
      otpTargetPhone = phone;
      otpTargetName = name;

      document.getElementById("otp-sms-banner").innerHTML =
        `OTP sent to <strong>${data.phone}</strong>. Verification code: <strong>${data.demo_otp}</strong>`;
      document.getElementById("otp-step-1").style.display = "none";
      document.getElementById("otp-step-2").style.display = "block";
      document.getElementById("login-otp-code").focus();
    } catch (e) {
      alert("OTP service error: " + e.message);
    }
  });

  document.getElementById("btn-verify-otp").addEventListener("click", async () => {
    const otp = document.getElementById("login-otp-code").value.trim();
    if (otp.length !== 4) {
      alert("Please enter the 4-digit OTP code.");
      return;
    }

    try {
      const res = await fetch("/api/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: otpTargetPhone,
          otp,
          otp_token: otpSessionToken,
          name: otpTargetName,
        }),
      });
      const data = await res.json();
      if (!data.verified) {
        alert(data.error || "Invalid OTP code.");
        return;
      }
      loggedInUser = data.user;
      localStorage.setItem("niffler_user", JSON.stringify(loggedInUser));
      loginModal.classList.remove("open");
      renderAuthNavbar();
    } catch (e) {
      alert("Verification error: " + e.message);
    }
  });

  renderAuthNavbar();

  // =========================================================================
  // 3. Carrier Monograms & Navigation
  // =========================================================================
  const CARRIER_COLORS = {
    "6E": "#1e40af",
    "AI": "#be123c",
    "QP": "#ea580c",
    "SG": "#dc2626",
    "IX": "#d97706",
    "IC": "#0284c7",
    "WY": "#0f766e",
    "UK": "#6b21a8",
  };

  function getCarrierBadge(airline, flightNo) {
    const code = (flightNo || "").split(/[-\s]/)[0].toUpperCase().slice(0, 2) || airline.slice(0, 2).toUpperCase();
    const bg = CARRIER_COLORS[code] || "#1e3a8a";
    return { code, bg };
  }

  const navTabs = document.querySelectorAll(".nf-nav-tab");
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

  // Trip Type toggle (One-way vs Round-trip)
  document.querySelectorAll(".radio-pill input").forEach(inp => {
    inp.addEventListener("change", () => {
      document.querySelectorAll(".radio-pill").forEach(p => p.classList.remove("active"));
      inp.closest(".radio-pill").classList.add("active");
      const isRound = inp.value === "roundtrip";
      const retBox = document.getElementById("box-return");
      const grid = document.getElementById("nf-search-grid");
      retBox.style.display = isRound ? "flex" : "none";
      grid.classList.toggle("roundtrip", isRound);
    });
  });

  document.querySelectorAll(".sf-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".sf-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
    });
  });

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

  document.getElementById("btn-toggle-trace").addEventListener("click", () => {
    const drawer = document.getElementById("agent-trace-drawer");
    drawer.style.display = drawer.style.display === "none" ? "block" : "none";
  });

  function updateTravelSearchUI() {
    const heroHeading = document.getElementById("hero-heading");
    const ctaBtn = document.getElementById("btn-search-travel");
    const sidebar = document.getElementById("ota-sidebar");
    const sortBar = document.getElementById("nf-sort-bar");
    const insightBar = document.getElementById("deal-insight-bar");
    const orig = document.getElementById("travel-origin");
    const dest = document.getElementById("travel-dest");
    const subO = document.getElementById("sub-origin");
    const subD = document.getElementById("sub-dest");

    if (currentTravelMode === "flights") {
      heroHeading.innerText = "Find the Lowest Airfares Across India & Beyond";
      ctaBtn.innerText = "SEARCH FLIGHTS";
      sidebar.style.display = "block";
      sortBar.style.display = "grid";
      insightBar.style.display = "flex";
      if (!orig.value) orig.value = "DEL";
      if (!dest.value) dest.value = "BLR";
      subO.innerText = "Origin Airport / City";
      subD.innerText = "Destination Airport / City";
    } else if (currentTravelMode === "hotels") {
      heroHeading.innerText = "Curated Stays, Boutique Villas & Resorts";
      ctaBtn.innerText = "FIND STAYS";
      sidebar.style.display = "none";
      sortBar.style.display = "none";
      insightBar.style.display = "none";
      dest.value = "GOA";
      subO.innerText = "Guest City";
      subD.innerText = "Destination City";
    } else if (currentTravelMode === "trains") {
      heroHeading.innerText = "IRCTC Rail Schedules, Live Berths & Tatkal";
      ctaBtn.innerText = "FIND TRAINS";
      sidebar.style.display = "none";
      sortBar.style.display = "none";
      insightBar.style.display = "none";
      orig.value = "NDLS";
      dest.value = "MMCT";
      subO.innerText = "Origin Railway Station";
      subD.innerText = "Destination Railway Station";
    } else if (currentTravelMode === "buses") {
      heroHeading.innerText = "Intercity Electric & Volvo Sleeper Coaches";
      ctaBtn.innerText = "FIND COACHES";
      sidebar.style.display = "none";
      sortBar.style.display = "none";
      insightBar.style.display = "none";
      orig.value = "BLR";
      dest.value = "HYD";
      subO.innerText = "Boarding City";
      subD.innerText = "Dropping City";
    }
  }

  // =========================================================================
  // 4. Live Search & Filters
  // =========================================================================
  document.getElementById("btn-search-travel").addEventListener("click", fetchTravelResults);

  async function fetchTravelResults() {
    const origin = document.getElementById("travel-origin").value.trim() || "DEL";
    const dest = document.getElementById("travel-dest").value.trim() || "BLR";
    const dateVal = depInput.value;
    const directOnly = document.getElementById("chk-direct-top").checked;
    const container = document.getElementById("travel-cards");

    container.innerHTML = `
      <div class="nf-card" style="padding:2.2rem; text-align:center; color:#64748b;">
        <strong>Searching live internet fares for ${origin.toUpperCase()} &rarr; ${dest.toUpperCase()}...</strong>
        <div style="font-size:0.8rem; margin-top:0.4rem;">Gemini 4 Hydrogen is scanning carriers &amp; promos for the lowest effective fare.</div>
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
        renderHotels(await res.json());
      } else if (currentTravelMode === "trains") {
        const res = await fetch(`/api/trains?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(dest)}`);
        renderTrains(await res.json());
      } else if (currentTravelMode === "buses") {
        const res = await fetch(`/api/buses?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(dest)}`);
        renderBuses(await res.json());
      }
    } catch (e) {
      container.innerHTML = `<div class="nf-card" style="padding:1.5rem; color:#dc2626;">Unable to load live results: ${e.message}</div>`;
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

    document.getElementById("agent-trace-list").innerHTML =
      (payload.agent_trace || []).map(step => `<li>${step}</li>`).join("");

    document.getElementById("cnt-stop-0").innerText = allFlights.filter(f => f.stops === 0).length;
    document.getElementById("cnt-stop-1").innerText = allFlights.filter(f => f.stops > 0).length;

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
      if (checkedStops.length > 0 && !checkedStops.includes(f.stops === 0 ? 0 : 1)) return false;
      if (f.price_inr > maxPrice) return false;
      if (activeAirlines.length > 0 && !activeAirlines.includes(f.airline)) return false;
      if (activeSlots.length > 0 && !activeSlots.some(s => matchesTimeSlot(f.departure_time, s))) return false;
      return true;
    });

    if (currentSort === "cheapest") list.sort((a, b) => a.price_inr - b.price_inr);
    else if (currentSort === "fastest") list.sort((a, b) => durToMins(a.duration) - durToMins(b.duration));
    else if (currentSort === "early") list.sort((a, b) => timeToMins(a.departure_time) - timeToMins(b.departure_time));
    else if (currentSort === "value") list.sort((a, b) => (a.price_inr + durToMins(a.duration) * 8) - (b.price_inr + durToMins(b.duration) * 8));

    renderFlights(list);
  }

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
      container.innerHTML = `<div class="nf-card" style="padding:2rem; text-align:center; color:#64748b;">No flights match current filters. Try clicking <strong>Clear All</strong>.</div>`;
      return;
    }

    container.innerHTML = "";
    flights.forEach(f => {
      const badge = getCarrierBadge(f.airline, f.flight_number);
      const stopsLabel = f.stops === 0 ? "Non-stop" : `${f.stops} stop`;
      const stopsClass = f.stops === 0 ? "nonstop" : "withstop";

      const card = document.createElement("div");
      card.className = "nf-card";
      card.innerHTML = `
        <div class="nf-card-main">
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
            <button type="button" class="btn-nf-book btn-book-flight">Select</button>
          </div>
        </div>
        <div class="nf-card-footer">
          <div class="footer-left">
            ${f.is_cheapest ? '<span class="cheapest-flag">Best Fare</span>' : ''}
            <span class="promo-pill">${f.promo_note || 'Zero gateway fee on UPI'}</span>
            <span>Cabin: ${f.cabin_baggage || '7 kg'} &bull; Check-in: ${f.checkin_baggage || '15 kg'}</span>
          </div>
          <span class="source-flag">${f.source || 'Live OTA Feed'}</span>
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
      card.className = "nf-card";
      card.innerHTML = `
        <div class="generic-card-main">
          <div>
            <div class="gc-title">${h.name} &bull; ${h.property_type}</div>
            <div class="gc-sub">${h.location}, ${h.city} &bull; ${h.user_rating}/5.0 (${h.reviews_count.toLocaleString()} reviews)</div>
            <div class="gc-tags">
              ${h.couple_friendly ? '<span class="gc-tag green">Couple Friendly</span>' : ''}
              ${h.free_cancellation ? '<span class="gc-tag">Free Cancellation</span>' : ''}
              ${(h.amenities || []).slice(0, 3).map(a => `<span class="gc-tag">${a}</span>`).join("")}
            </div>
          </div>
          <div class="price-col">
            <div class="price-wrap">
              <div class="p-amt">&#8377;${h.price_per_night_inr.toLocaleString()}</div>
              <div class="p-sub">per night</div>
            </div>
            <button type="button" class="btn-nf-book btn-book-hotel">Select Room</button>
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
      card.className = "nf-card";
      card.innerHTML = `
        <div class="generic-card-main">
          <div>
            <div class="gc-title">${t.train_number} &bull; ${t.train_name}</div>
            <div class="gc-sub">${t.origin_station} (${t.departure_time}) &rarr; ${t.destination_station} (${t.arrival_time}) &bull; ${t.travel_time}</div>
            <div class="gc-tags">${classesHtml}</div>
          </div>
          <div class="price-col">
            <a href="https://www.irctc.co.in/nget/train-search" target="_blank" class="btn-nf-book">IRCTC Portal</a>
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
      card.className = "nf-card";
      card.innerHTML = `
        <div class="generic-card-main">
          <div>
            <div class="gc-title">${b.operator} &bull; ${b.bus_type}</div>
            <div class="gc-sub">${b.origin} (${b.departure_time}) &rarr; ${b.destination} (${b.arrival_time}) &bull; ${b.duration} &bull; ${b.boarding_point}</div>
            <div class="gc-tags">
              <span class="gc-tag green">${b.rating} Rating</span>
              <span class="gc-tag">${b.seats_left} seats left</span>
            </div>
          </div>
          <div class="price-col">
            <div class="price-wrap">
              <div class="p-amt">&#8377;${b.price_inr.toLocaleString()}</div>
              <div class="p-sub">per seat</div>
            </div>
            <a href="${b.booking_url}" target="_blank" class="btn-nf-book">Book Seat</a>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  }

  // =========================================================================
  // 5. Guest / Logged-In Booking Handoff Modal
  // =========================================================================
  async function openPaymentModal(type, item) {
    const nameInput = document.getElementById("m-input-name");
    const phoneInput = document.getElementById("m-input-phone");
    const emailInput = document.getElementById("m-input-email");
    const ageInput = document.getElementById("m-input-age");

    // Pre-fill ONLY if user explicitly signed in via Mobile OTP
    if (loggedInUser) {
      if (!nameInput.value) nameInput.value = loggedInUser.name || "";
      if (!phoneInput.value) phoneInput.value = loggedInUser.phone || "";
    }

    const payload = type === "hotel"
      ? {
          type: "hotel",
          hotel_name: item.name,
          city: item.city,
          nights: 1,
          price: item.price_per_night_inr,
          passenger_name: nameInput.value,
          contact_phone: phoneInput.value,
          contact_email: emailInput.value,
        }
      : {
          type: "flight",
          airline: item.airline,
          flight_number: item.flight_number,
          origin: item.origin,
          destination: item.destination,
          fare: item.price_inr,
          passenger_name: nameInput.value,
          contact_phone: phoneInput.value,
          contact_email: emailInput.value,
          passenger_age: parseInt(ageInput.value) || 28,
        };

    try {
      const res = await fetch("/api/booking/handoff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const sess = await res.json();

      document.getElementById("modal-item-title").innerHTML = sess.item_title;
      document.getElementById("m-sess-id").innerText = sess.session_id;

      const baseFare = item.base_fare_inr > 0 ? item.base_fare_inr : sess.amount_inr;
      const taxesAmt = item.taxes_inr > 0 ? item.taxes_inr : sess.taxes_inr;
      document.getElementById("m-base-fare").innerText = `₹${baseFare.toLocaleString()}`;
      document.getElementById("m-taxes").innerText = `₹${taxesAmt.toLocaleString()}`;
      document.getElementById("m-conv-fee").innerText = `₹${sess.convenience_fee_inr.toLocaleString()}`;
      document.getElementById("m-total-amt").innerText =
        `₹${(item.base_fare_inr > 0 ? item.price_inr + sess.convenience_fee_inr : sess.total_payable_inr).toLocaleString()}`;

      document.getElementById("btn-goto-partner").href = item.booking_url || sess.payment_gateway_url;
      document.getElementById("btn-goto-payment").href = sess.payment_gateway_url;

      document.getElementById("booking-modal").classList.add("open");
    } catch (e) {
      alert("Booking handoff error: " + e.message);
    }
  }

  document.getElementById("btn-close-modal").addEventListener("click", () => {
    document.getElementById("booking-modal").classList.remove("open");
  });

  // =========================================================================
  // 6. ITR Optimizer & EPF Explorer
  // =========================================================================
  let lastITRJson = null;
  document.getElementById("btn-calc-itr").addEventListener("click", async () => {
    const name = document.getElementById("itr-name").value.trim() || (loggedInUser ? loggedInUser.name : "Taxpayer");
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
          name,
        }),
      });
      const data = await res.json();
      lastITRJson = data.itr_1_json;

      document.getElementById("itr-results").style.display = "block";
      const isNew = data.recommended_regime === "NEW_REGIME";
      document.getElementById("showdown-banner").innerHTML =
        `Recommended: <strong>${isNew ? "New Tax Regime" : "Old Tax Regime"}</strong> &bull; Saves <strong>₹${data.tax_savings_inr.toLocaleString()}</strong> in tax`;

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
        <li><strong>Form 31 (Housing):</strong> ${data.eligibility.form_31_housing.eligible ? "ELIGIBLE — " : "NOT ELIGIBLE — "}${data.eligibility.form_31_housing.rule}</li>
        <li><strong>Form 31 (Marriage):</strong> ${data.eligibility.form_31_marriage.eligible ? "ELIGIBLE — " : "NOT ELIGIBLE — "}${data.eligibility.form_31_marriage.rule}</li>
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
