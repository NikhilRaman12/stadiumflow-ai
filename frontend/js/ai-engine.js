// ═══════════════════════════════════════════════════════════════
// STADIUMIQ AI ENGINE — Dynamic Backend Proxy Integration
// FIFA World Cup 2026
// ═══════════════════════════════════════════════════════════════

const AIEngine = (() => {

  // Stadium Knowledge Base — RAG source for ARIA
  const STADIUM_KB = {
    venues: [
      { id: 'met', name: 'MetLife Stadium', city: 'New York/New Jersey', capacity: 82500, country: 'USA', gates: ['A','B','C','D','E','F'], zones: ['North','South','East','West','Field Level','Upper Deck'], accessible_gates: ['A','C'], medical_stations: 8, capacity_zones: { 'North': 82, 'South': 45, 'East': 67, 'West': 78, 'Field Level': 90, 'Upper Deck': 55 } },
      { id: 'dal', name: 'AT&T Stadium', city: 'Dallas', capacity: 80000, country: 'USA', gates: ['1','2','3','4'], zones: ['Plaza', 'Club', 'Suite', 'Upper'], accessible_gates: ['1','3'], medical_stations: 6, capacity_zones: { 'Plaza': 70, 'Club': 55, 'Suite': 30, 'Upper': 60 } },
      { id: 'la',  name: 'SoFi Stadium', city: 'Los Angeles', capacity: 70000, country: 'USA', gates: ['North','South','East','West'], zones: ['Main Concourse','Club Level','Terrace','End Zone'], accessible_gates: ['North','South'], medical_stations: 7, capacity_zones: { 'Main Concourse': 65, 'Club Level': 40, 'Terrace': 80, 'End Zone': 75 } },
      { id: 'bc',  name: 'BC Place', city: 'Vancouver', capacity: 54500, country: 'Canada', gates: ['A','B','C','D'], zones: ['Main Bowl','Upper Bowl','Club'], accessible_gates: ['A','B'], medical_stations: 5, capacity_zones: { 'Main Bowl': 72, 'Upper Bowl': 50, 'Club': 35 } },
      { id: 'atz', name: 'Estadio Azteca', city: 'Mexico City', capacity: 87523, country: 'Mexico', gates: ['Norte','Sur','Este','Oeste'], zones: ['Cancha','Gradería','Palco','General'], accessible_gates: ['Norte','Sur'], medical_stations: 10, capacity_zones: { 'Cancha': 95, 'Gradería': 80, 'Palco': 40, 'General': 85 } },
    ],
    languages: ['English','Spanish','French','Portuguese','German','Arabic','Chinese','Japanese','Korean','Hindi','Italian','Dutch','Russian','Turkish','Polish','Swedish','Norwegian','Danish','Finnish','Greek','Czech','Romanian','Hungarian','Croatian','Serbian','Ukrainian','Thai','Vietnamese','Indonesian','Malay','Bengali','Swahili'],
    services: {
      medical: 'Medical stations located at each gate entrance. For emergencies: call 911 (USA), 911 (Canada), 911 (Mexico). On-site first aid available 24/7.',
      lost_found: 'Lost & Found center at Gate A (main entrance) — open 2hrs before and 2hrs after each match.',
      food: 'Concessions on every level. App queue predictions updated every 5 minutes.',
      transport: 'Shuttles, metro, and bus connections. App shows live wait times and platform capacities.',
      accessibility: 'Wheelchair access at designated gates. Accessible seating, restrooms on all levels. ASL interpreters available on request.',
    },
    match_schedule: [
      { date: '2026-06-11', home: 'Mexico', away: 'FIFA XI', venue: 'Estadio Azteca', time: '20:00 local' },
      { date: '2026-06-13', home: 'USA', away: 'Serbia', venue: 'MetLife Stadium', time: '21:00 local' },
      { date: '2026-06-14', home: 'Canada', away: 'Morocco', venue: 'BC Place', time: '18:00 local' },
    ]
  };

  // Call Backend proxy instead of direct googleapis.com
  async function generateContent(prompt, systemRole = 'aria_fan', options = {}) {
    const apiKey = localStorage.getItem('stadiumiq_gemini_key') || '';
    const backendUrl = localStorage.getItem('stadiumiq_backend_url') || '';
    const BACKEND_URL = backendUrl || window.location.origin;

    try {
      const response = await fetch(`${BACKEND_URL}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-Gemini-API-Key': apiKey } : {})
        },
        body: JSON.stringify({
          message: prompt,
          session_id: options.sessionId || 'gen-' + Math.random().toString(36).substr(2, 9),
          venue_id: options.venueId || 'met',
          role: systemRole.includes('ops') || systemRole.includes('analyzer') ? 'ops' : 'fan',
          context: {}
        })
      });

      if (!response.ok) {
        return { success: false, text: getDemoResponse(prompt), simulated: true };
      }

      const data = await response.json();
      return { success: true, text: data.response, simulated: data.simulated || false };
    } catch (e) {
      console.error('generateContent proxy error:', e);
      return { success: false, text: getDemoResponse(prompt), simulated: true };
    }
  }

  // Multi-turn conversation handler proxied to backend
  async function chat(messages, systemRole = 'aria_fan', options = {}) {
    const apiKey = localStorage.getItem('stadiumiq_gemini_key') || '';
    const backendUrl = localStorage.getItem('stadiumiq_backend_url') || '';
    const BACKEND_URL = backendUrl || window.location.origin;

    const lastMsg = messages[messages.length - 1]?.text || messages[messages.length - 1]?.content || '';

    try {
      const response = await fetch(`${BACKEND_URL}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-Gemini-API-Key': apiKey } : {})
        },
        body: JSON.stringify({
          message: lastMsg,
          session_id: options.sessionId || 'chat-' + Math.random().toString(36).substr(2, 9),
          venue_id: options.venueId || 'met',
          role: systemRole.includes('ops') ? 'ops' : 'fan',
          context: {}
        })
      });

      if (!response.ok) {
        return { success: false, text: getDemoResponse(lastMsg), simulated: true };
      }

      const data = await response.json();
      return { success: true, text: data.response, simulated: data.simulated || false };
    } catch (e) {
      console.error('chat proxy error:', e);
      return { success: false, text: getDemoResponse(lastMsg), simulated: true };
    }
  }

  // Demo responses when no API key (simulated mode)
  function getDemoResponse(query) {
    const q = query.toLowerCase();
    if (q.includes('seat') || q.includes('asiento') || q.includes('siège')) {
      return '🎯 To find your seat: Check your ticket QR code for Gate letter + Section + Row. Follow the colored pathways from your gate entrance. Stadium staff are positioned at every junction! Your seat map is in the "My Tickets" section below. 🏟️';
    }
    if (q.includes('food') || q.includes('eat') || q.includes('comida') || q.includes('manger')) {
      return '🍔 Concessions are on every level! Current queue times: Level 1 (8 min), Level 2 (4 min ✅ BEST), Level 3 (12 min). Fan favorites: loaded nachos, local food trucks at the North Plaza. EcoScore tip: the veggie burger saves 2.1kg CO₂ vs beef! 🌱';
    }
    if (q.includes('wheelchair') || q.includes('accessible') || q.includes('fauteuil') || q.includes('silla de ruedas')) {
      return '♿ Wheelchair-accessible entrance: Gate A (main entrance, level access). Elevators on all levels — press the blue button. Accessible seating: Section F, Rows 1-2 (excellent sightlines). Accessible restrooms on every concourse. Need an escort? Press the help button at any accessible entrance — staff arrive within 3 minutes.';
    }
    if (q.includes('transport') || q.includes('bus') || q.includes('metro') || q.includes('parking')) {
      return '🚌 Best transport options right now:\n• Metro Line 3: 12-min wait, low crowd ✅\n• Shuttle Bus Zone C: 6-min wait ✅\n• Parking Zone A: 95% full ❌ → Redirect to Zone D (40% full)\n\nPost-match: Plan for 25-min crowd dispersal. Metro is fastest — skip Zone A exit tonight.';
    }
    if (q.includes('emergency') || q.includes('medical') || q.includes('help') || q.includes('sick')) {
      return '🚨 MEDICAL EMERGENCY: Nearest first aid station is at Gate B entrance (2 min walk). For serious emergencies: call 911 or press the RED help button on any stadium column. AED defibrillators are at every gate and every 100m on concourses. Stadium medical team response time: < 4 minutes. Stay calm — help is on the way! 💙';
    }
    if (q.includes('carbon') || q.includes('eco') || q.includes('green') || q.includes('sustainability')) {
      return '🌱 Your EcoScore today: Great choices! Taking the metro saved 4.2kg CO₂ vs driving. Your food choices this match: 2.8kg CO₂. Total matchday footprint: 7.1kg CO₂.\n\nGlobal tip: If all 80,000 fans chose metro over car, we\'d save 336 tonnes of CO₂ — equivalent to planting 15,000 trees! 🌳';
    }
    return `🤖 Hi! I'm ARIA, your FIFA World Cup 2026 AI assistant. I can help with:\n• 🎯 Seat & navigation guidance\n• 🍔 Concession recommendations  \n• ♿ Accessibility routing\n• 🚌 Transport & parking\n• 🌱 EcoScore & sustainability\n• 🚨 Safety & emergency info\n\nAdd your Gemini API key in Settings for full AI-powered responses in 32 languages! What can I help you with?`;
  }

  // Structured AI outputs via backend
  async function analyzeIncident(description, location, severity_hint) {
    const apiKey = localStorage.getItem('stadiumiq_gemini_key') || '';
    const backendUrl = localStorage.getItem('stadiumiq_backend_url') || '';
    const BACKEND_URL = backendUrl || window.location.origin;

    try {
      const response = await fetch(`${BACKEND_URL}/api/incidents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-Gemini-API-Key': apiKey } : {})
        },
        body: JSON.stringify({
          description: description,
          location: location,
          venue_id: 'met',
          severity_hint: parseInt(severity_hint) || 3
        })
      });

      if (response.ok) {
        const data = await response.json();
        return { success: true, text: JSON.stringify(data.ai_assessment, null, 2), parsed: data.ai_assessment, simulated: false };
      }
    } catch (e) {
      console.error('analyzeIncident proxy error:', e);
    }
    
    // simulated fallback
    const mockAssessment = {
      severity: parseInt(severity_hint) || 3,
      severity_label: 'MEDIUM',
      immediate_action: 'Assess and monitor',
      resources_needed: ['Security', 'Medical'],
      estimated_resolution: '15-20 min',
      escalate_to: ['Duty Manager'],
      crowd_impact: 'LOW',
      evacuation_needed: false
    };
    return { success: true, text: JSON.stringify(mockAssessment, null, 2), parsed: mockAssessment, simulated: true };
  }

  async function buildItinerary(preferences) {
    const prompt = `Build a personalized FIFA World Cup 2026 matchday itinerary for this fan:
Match: ${preferences.match} at ${preferences.venue}
Kick-off: ${preferences.kickoff}
Seat: ${preferences.seat}
Group size: ${preferences.groupSize}
Accessibility needs: ${preferences.accessibility || 'none'}
Food preferences: ${preferences.food || 'no preference'}
Arriving from: ${preferences.origin}

Create a detailed timeline starting 3 hours before kick-off through post-match departure. Include specific times, locations, and AI tips.`;
    return generateContent(prompt, 'itinerary_builder');
  }

  async function getEcoAdvice(travelData) {
    const apiKey = localStorage.getItem('stadiumiq_gemini_key') || '';
    const backendUrl = localStorage.getItem('stadiumiq_backend_url') || '';
    const BACKEND_URL = backendUrl || window.location.origin;

    try {
      const response = await fetch(`${BACKEND_URL}/api/eco/score`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-Gemini-API-Key': apiKey } : {})
        },
        body: JSON.stringify({
          venue_id: 'met',
          travel_mode: travelData.transport || 'metro',
          travel_distance: parseFloat(travelData.distance) || 25.0,
          group_size: parseInt(travelData.groupSize) || 1,
          food_choices: travelData.food ? [travelData.food] : ['local_food']
        })
      });

      if (response.ok) {
        const data = await response.json();
        return { success: true, text: data.advice, simulated: false, data: data };
      }
    } catch (e) {
      console.error('getEcoAdvice proxy error:', e);
    }
    return { success: false, text: getDemoResponse('eco'), simulated: true };
  }

  return { generateContent, chat, analyzeIncident, buildItinerary, getEcoAdvice, getDemoResponse, STADIUM_KB };
})();

// Export globally
window.AIEngine = AIEngine;
