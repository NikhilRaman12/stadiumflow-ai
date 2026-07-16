// ═══════════════════════════════════════════════════════════════
// STADIUMIQ AI ENGINE — Gemini 1.5 Pro Integration
// FIFA World Cup 2026
// ═══════════════════════════════════════════════════════════════

const AIEngine = (() => {

  const GEMINI_BASE = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent';

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

  const SYSTEM_PROMPTS = {
    aria_fan: `You are ARIA, the AI assistant for StadiumIQ at FIFA World Cup 2026.
You help fans navigate stadiums, find services, get match info, plan their day, and stay safe.
Be friendly, concise, and always safety-first. Support all 32 languages — respond in the user's language automatically.
Stadium data: ${JSON.stringify(STADIUM_KB.venues)}.
Services: ${JSON.stringify(STADIUM_KB.services)}.
Format responses with emojis for quick scanning. Keep replies under 150 words unless complex routing is needed.
If crowd density is high in an area, proactively suggest alternatives.`,

    aria_ops: `You are ARIA, the AI operational intelligence assistant for FIFA World Cup 2026 venue staff.
You provide real-time crowd analysis, incident assessment, staff deployment recommendations, and safety protocols.
Be precise, data-driven, and use operational language. Prioritize safety and efficiency.
Stadium data: ${JSON.stringify(STADIUM_KB.venues)}.
Always include: risk level (LOW/MEDIUM/HIGH/CRITICAL), recommended action, and time-to-act.`,

    aria_volunteer: `You are ARIA, the volunteer support assistant for FIFA World Cup 2026.
You help volunteers with fan queries, zone assignments, incident reporting, and accessibility support.
Be clear, actionable, and empathetic. Provide step-by-step guidance when needed.
Stadium data: ${JSON.stringify(STADIUM_KB.venues)}.
Services: ${JSON.stringify(STADIUM_KB.services)}.`,

    eco_advisor: `You are the EcoScore sustainability advisor for FIFA World Cup 2026.
Analyze fan travel and consumption choices. Provide carbon footprint estimates, sustainable alternatives, and eco-friendly venue recommendations.
Use actual CO2 data: flight per km = 0.255kg CO2/km, car = 0.171kg/km, bus = 0.089kg/km, metro = 0.041kg/km.
Be encouraging, not preachy. Reward eco choices with points. Keep responses positive and actionable.`,

    itinerary_builder: `You are a personalized matchday itinerary builder for FIFA World Cup 2026.
Create detailed, time-sequenced matchday plans for fans. Include arrival strategy, pre-match activities, concession timing, transport plans.
Optimize for: match kick-off time, seat location, accessible needs, food preferences, group size.
Output as a structured timeline with times and locations.`,

    incident_analyzer: `You are an AI incident analyst for FIFA World Cup 2026 venue operations.
Analyze incident reports, assess severity (1-5 scale), recommend response protocols, and escalation paths.
Use FIFA stadium safety protocols. Reference emergency services: Medical (EMS), Security, Fire Safety, Crowd Management, Logistics.
Always provide: severity score, immediate action, resources needed, estimated resolution time.`,
  };

  // Call Gemini API
  async function generateContent(prompt, systemRole = 'aria_fan', options = {}) {
    const apiKey = localStorage.getItem('stadiumiq_gemini_key');
    if (!apiKey) {
      return { success: false, text: '⚠️ No API key configured. Please add your Gemini API key in Settings to enable AI features.', simulated: true };
    }

    const systemPrompt = SYSTEM_PROMPTS[systemRole] || SYSTEM_PROMPTS.aria_fan;

    const requestBody = {
      contents: [
        {
          role: 'user',
          parts: [{ text: `${systemPrompt}\n\n---\nUSER QUERY: ${prompt}` }]
        }
      ],
      generationConfig: {
        temperature: options.temperature || 0.7,
        topK: 40,
        topP: 0.95,
        maxOutputTokens: options.maxTokens || 512,
        stopSequences: [],
      },
      safetySettings: [
        { category: 'HARM_CATEGORY_HARASSMENT', threshold: 'BLOCK_MEDIUM_AND_ABOVE' },
        { category: 'HARM_CATEGORY_HATE_SPEECH', threshold: 'BLOCK_MEDIUM_AND_ABOVE' },
      ]
    };

    try {
      const response = await fetch(`${GEMINI_BASE}?key=${apiKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const err = await response.json();
        const msg = err?.error?.message || `API error ${response.status}`;
        if (response.status === 400 && msg.includes('API_KEY')) {
          return { success: false, text: '🔑 Invalid API key. Please check your Gemini API key in Settings.', simulated: true };
        }
        return { success: false, text: `⚠️ AI Error: ${msg}`, simulated: true };
      }

      const data = await response.json();
      const text = data?.candidates?.[0]?.content?.parts?.[0]?.text;

      if (!text) return { success: false, text: '⚠️ No response from AI. Please try again.', simulated: true };

      return { success: true, text: text.trim(), simulated: false };

    } catch (err) {
      console.error('Gemini API error:', err);
      return { success: false, text: `⚠️ Connection error: ${err.message}. Check your internet connection.`, simulated: true };
    }
  }

  // Multi-turn conversation handler
  async function chat(messages, systemRole = 'aria_fan', options = {}) {
    const apiKey = localStorage.getItem('stadiumiq_gemini_key');
    if (!apiKey) {
      return { success: false, text: getDemoResponse(messages[messages.length-1]?.text || ''), simulated: true };
    }

    const systemPrompt = SYSTEM_PROMPTS[systemRole] || SYSTEM_PROMPTS.aria_fan;

    const contents = [
      { role: 'user', parts: [{ text: systemPrompt + '\n\nYou are now starting a conversation. Respond naturally to each message.' }] },
      { role: 'model', parts: [{ text: 'Understood. I am ARIA, ready to assist fans and staff at FIFA World Cup 2026.' }] },
      ...messages.map(m => ({
        role: m.role === 'user' ? 'user' : 'model',
        parts: [{ text: m.text }]
      }))
    ];

    try {
      const response = await fetch(`${GEMINI_BASE}?key=${apiKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents,
          generationConfig: { temperature: options.temperature || 0.75, maxOutputTokens: options.maxTokens || 600 },
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        return { success: false, text: getDemoResponse(messages[messages.length-1]?.text || ''), simulated: true, error: err?.error?.message };
      }

      const data = await response.json();
      const text = data?.candidates?.[0]?.content?.parts?.[0]?.text;
      return { success: true, text: text?.trim() || '⚠️ Empty response', simulated: false };

    } catch (err) {
      return { success: false, text: getDemoResponse(messages[messages.length-1]?.text || ''), simulated: true };
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

  // Structured AI outputs
  async function analyzeIncident(description, location, severity_hint) {
    const prompt = `Analyze this stadium incident and provide a JSON response:
Incident: ${description}
Location: ${location}
Initial severity estimate: ${severity_hint}

Respond with ONLY valid JSON in this exact format:
{
  "severity": 1-5,
  "severity_label": "LOW|MEDIUM|HIGH|CRITICAL|EXTREME",
  "immediate_action": "string",
  "resources_needed": ["array", "of", "resources"],
  "estimated_resolution": "time string",
  "escalate_to": ["departments"],
  "crowd_impact": "LOW|MEDIUM|HIGH",
  "evacuation_needed": true/false
}`;
    const result = await generateContent(prompt, 'incident_analyzer', { temperature: 0.3, maxTokens: 400 });
    if (result.success) {
      try {
        const jsonMatch = result.text.match(/\{[\s\S]*\}/);
        if (jsonMatch) return { ...result, parsed: JSON.parse(jsonMatch[0]) };
      } catch (e) { /* fallback */ }
    }
    return { ...result, parsed: { severity: 3, severity_label: 'MEDIUM', immediate_action: 'Assess and monitor', resources_needed: ['Security', 'Medical'], estimated_resolution: '15-20 min', escalate_to: ['Duty Manager'], crowd_impact: 'LOW', evacuation_needed: false } };
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
    return generateContent(prompt, 'itinerary_builder', { temperature: 0.8, maxTokens: 700 });
  }

  async function getEcoAdvice(travelData) {
    const prompt = `Calculate and advise on carbon footprint for this fan's World Cup journey:
Travel to stadium: ${travelData.transport} (${travelData.distance}km)
Origin: ${travelData.origin}
Food choices today: ${travelData.food}
Group size: ${travelData.groupSize}

Provide CO2 estimate, comparison to average fan, eco tips, and EcoScore (0-100).`;
    return generateContent(prompt, 'eco_advisor', { temperature: 0.6, maxTokens: 400 });
  }

  return { generateContent, chat, analyzeIncident, buildItinerary, getEcoAdvice, getDemoResponse, STADIUM_KB, SYSTEM_PROMPTS };
})();

// Export globally
window.AIEngine = AIEngine;
