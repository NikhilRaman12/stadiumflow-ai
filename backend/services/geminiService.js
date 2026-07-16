// ═══════════════════════════════════════════════
// Gemini AI Service — StadiumIQ Backend
// ═══════════════════════════════════════════════
const { GoogleGenerativeAI, HarmCategory, HarmBlockThreshold } = require('@google/generative-ai');
const logger = require('../middleware/logger');
const stadiums = require('../data/stadiums.json');

let genAI = null;
let model = null;

function initGemini() {
  const key = process.env.GEMINI_API_KEY;
  if (!key) { logger.warn('GEMINI_API_KEY not set — AI features disabled'); return false; }
  genAI = new GoogleGenerativeAI(key);
  model = genAI.getGenerativeModel({
    model: 'gemini-1.5-pro',
    safetySettings: [
      { category: HarmCategory.HARM_CATEGORY_HARASSMENT,   threshold: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE },
      { category: HarmCategory.HARM_CATEGORY_HATE_SPEECH,  threshold: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE },
    ],
  });
  logger.info('Gemini 1.5 Pro initialized');
  return true;
}
initGemini();

const SYSTEM_PROMPTS = {
  aria_fan: `You are ARIA, the official AI assistant for StadiumIQ at FIFA World Cup 2026.
Help fans navigate stadiums, find services, get match info, and stay safe.
Be friendly, concise, multilingual. Respond in the user's language automatically.
Stadium knowledge: ${JSON.stringify(stadiums.slice(0, 3))}.
Use emojis for quick scanning. Keep replies under 150 words unless routing needed.
Always prioritize safety. If crowd is high somewhere, suggest alternatives.`,

  aria_ops: `You are ARIA Operations AI for FIFA World Cup 2026 venue management.
Provide crowd analysis, incident assessment, staff deployment recommendations.
Be precise, data-driven. Use operational terminology.
Always include: RISK LEVEL, RECOMMENDED ACTION, TIME-TO-ACT, RESOURCES.
Stadium data: ${JSON.stringify(stadiums)}.`,

  aria_volunteer: `You are ARIA, the volunteer support AI for FIFA World Cup 2026.
Help volunteers answer fan queries, handle zone assignments, support accessibility needs.
Be clear, empathetic, and provide step-by-step guidance.
Stadium services: Medical at each gate, Lost&Found at Gate A, Accessible entrances at Gates A & C.`,

  eco: `You are the EcoScore sustainability advisor for FIFA World Cup 2026.
Calculate carbon footprints. CO2 rates: flight=0.255kg/km, car=0.171kg/km, bus=0.089kg/km, metro=0.041kg/km.
Be encouraging. Reward eco-choices with points. Keep responses positive and actionable.`,

  itinerary: `You are a matchday itinerary planner for FIFA World Cup 2026.
Build detailed time-sequenced plans: arrival strategy, pre-match, concessions, transport.
Output as structured timeline. Optimize for kick-off time, seat location, group size, accessibility.`,

  incident: `You are an AI incident analyst for FIFA World Cup 2026 stadium safety.
Analyze incidents, score severity 1-5, recommend response. Use FIFA safety protocols.
Always output JSON: { severity, severity_label, immediate_action, resources_needed, estimated_resolution, escalate_to, crowd_impact, evacuation_needed }`,

  crowd_analysis: `You are a crowd dynamics AI for FIFA World Cup 2026.
Analyze crowd patterns, predict bottlenecks, recommend flow optimizations.
Consider: gate capacities, time before/after match, weather, match importance.
Output actionable recommendations for operations staff.`,
};

async function generateContent(prompt, role = 'aria_fan', options = {}) {
  if (!model) return { success: false, text: simulatedResponse(prompt, role), simulated: true };
  try {
    const fullPrompt = `${SYSTEM_PROMPTS[role] || SYSTEM_PROMPTS.aria_fan}\n\n---\nUSER: ${prompt}`;
    const result = await model.generateContent({
      contents: [{ role: 'user', parts: [{ text: fullPrompt }] }],
      generationConfig: {
        temperature:     options.temperature   || 0.75,
        topK:            40,
        topP:            0.95,
        maxOutputTokens: options.maxTokens     || 512,
      },
    });
    const text = result.response.text();
    logger.info(`Gemini [${role}] — ${prompt.substring(0, 60)}...`);
    return { success: true, text, simulated: false };
  } catch (err) {
    logger.error(`Gemini error: ${err.message}`);
    return { success: false, text: simulatedResponse(prompt, role), simulated: true, error: err.message };
  }
}

async function chat(history, newMessage, role = 'aria_fan', options = {}) {
  if (!model) return { success: false, text: simulatedResponse(newMessage, role), simulated: true };
  try {
    const chat = model.startChat({
      history: [
        { role: 'user',  parts: [{ text: SYSTEM_PROMPTS[role] || SYSTEM_PROMPTS.aria_fan }] },
        { role: 'model', parts: [{ text: 'Understood. I am ARIA, ready to assist at FIFA World Cup 2026.' }] },
        ...history.map(m => ({ role: m.role, parts: [{ text: m.content }] })),
      ],
      generationConfig: { temperature: options.temperature || 0.75, maxOutputTokens: options.maxTokens || 600 },
    });
    const result = await chat.sendMessage(newMessage);
    return { success: true, text: result.response.text(), simulated: false };
  } catch (err) {
    logger.error(`Gemini chat error: ${err.message}`);
    return { success: false, text: simulatedResponse(newMessage, role), simulated: true };
  }
}

async function analyzeIncident(description, location, severity_hint) {
  const prompt = `Analyze this stadium incident. Respond ONLY with valid JSON.
Incident: ${description}
Location: ${location}
Initial severity: ${severity_hint}
JSON format: {"severity":1-5,"severity_label":"LOW|MEDIUM|HIGH|CRITICAL|EXTREME","immediate_action":"string","resources_needed":["array"],"estimated_resolution":"string","escalate_to":["departments"],"crowd_impact":"LOW|MEDIUM|HIGH","evacuation_needed":false}`;
  const result = await generateContent(prompt, 'incident', { temperature: 0.2, maxTokens: 300 });
  if (result.success) {
    try {
      const match = result.text.match(/\{[\s\S]*\}/);
      if (match) return { ...result, parsed: JSON.parse(match[0]) };
    } catch (e) { /* fallback */ }
  }
  return { ...result, parsed: { severity: 3, severity_label: 'MEDIUM', immediate_action: 'Assess situation and monitor', resources_needed: ['Security', 'Medical'], estimated_resolution: '15-20 min', escalate_to: ['Duty Manager'], crowd_impact: 'LOW', evacuation_needed: false } };
}

async function buildItinerary(preferences) {
  const prompt = `Build a FIFA World Cup 2026 matchday itinerary:
Match: ${preferences.match} | Venue: ${preferences.venue} | Kick-off: ${preferences.kickoff}
Seat: ${preferences.seat} | Group: ${preferences.groupSize} people
Accessibility: ${preferences.accessibility || 'none'} | Origin: ${preferences.origin}
Food prefs: ${preferences.food || 'any'}
Create timeline from 3hrs before kick-off to post-match departure with times, locations, tips.`;
  return generateContent(prompt, 'itinerary', { temperature: 0.8, maxTokens: 800 });
}

async function analyzeCrowd(zoneData, timeContext) {
  const prompt = `Analyze these crowd conditions and provide operational recommendations:
Zone data: ${JSON.stringify(zoneData)}
Time context: ${timeContext}
Provide 3-5 specific recommendations with priority levels.`;
  return generateContent(prompt, 'crowd_analysis', { temperature: 0.5, maxTokens: 500 });
}

// Simulated responses (when no API key)
function simulatedResponse(query, role) {
  if (role === 'aria_ops') {
    return `⚡ OPERATIONAL ANALYSIS\nRisk Level: MEDIUM\nCurrent crowd density is within acceptable parameters. Gate D showing 78% capacity — recommend pre-emptive flow redistribution to Gate E (32% capacity). Deploy 2 additional stewards to concourse junction. Time to act: NOW.\nEstimated impact: -15% congestion in 8 minutes.`;
  }
  const q = (query || '').toLowerCase();
  if (q.includes('seat')) return '🎯 Follow the colored pathways from your gate to your section. Check ticket QR for Gate + Section + Row. Staff at every junction!';
  if (q.includes('food') || q.includes('eat')) return '🍔 Best queue right now: Level 2 (4 min ✅). Level 1 (8 min). Level 3 (12 min). Veggie option saves 2.1kg CO₂! 🌱';
  if (q.includes('wheelchair') || q.includes('accessible')) return '♿ Accessible entrance: Gate A (level access, ramp available). Lifts on all levels. Accessible seating: Section F, Rows 1-2. Need escort? Press help button at Gate A.';
  if (q.includes('transport') || q.includes('bus') || q.includes('metro')) return '🚌 Metro Line 3: 12-min wait ✅ | Shuttle Zone C: 6-min ✅ | Parking A: 95% full ❌ → Use Zone D (40% full)';
  return `🤖 Hi! I'm ARIA — your FIFA World Cup 2026 AI assistant!\n\n I can help with:\n• 🎯 Seat & navigation\n• 🍔 Concessions & queues\n• ♿ Accessibility routing\n• 🚌 Transport & parking\n• 🌱 EcoScore tracking\n• 🚨 Safety & emergency\n\nSet GEMINI_API_KEY for full AI capabilities in 32 languages!`;
}

module.exports = { generateContent, chat, analyzeIncident, buildItinerary, analyzeCrowd };
