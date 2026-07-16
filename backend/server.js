// ═══════════════════════════════════════════════════════════════
// STADIUMIQ BACKEND SERVER
// FIFA World Cup 2026 — GenAI Operations Platform
// Node.js + Express + Socket.io + Google Gemini
// ═══════════════════════════════════════════════════════════════
require('dotenv').config();
const express      = require('express');
const http         = require('http');
const { Server }   = require('socket.io');
const cors         = require('cors');
const helmet       = require('helmet');
const morgan       = require('morgan');
const rateLimit    = require('express-rate-limit');
const path         = require('path');
const logger       = require('./middleware/logger');

// Routes
const aiRoutes         = require('./routes/ai');
const crowdRoutes      = require('./routes/crowd');
const transportRoutes  = require('./routes/transport');
const incidentRoutes   = require('./routes/incidents');
const staffRoutes      = require('./routes/staff');
const ecoRoutes        = require('./routes/eco');
const analyticsRoutes  = require('./routes/analytics');

// Services
const CrowdSimulator      = require('./services/crowdSimulator');
const TransportOptimizer  = require('./services/transportOptimizer');
const IncidentManager     = require('./services/incidentManager');

const app    = express();
const server = http.createServer(app);
const io     = new Server(server, {
  cors: { origin: '*', methods: ['GET', 'POST'] }
});

const PORT = process.env.PORT || 3001;

// ── MIDDLEWARE ─────────────────────────────────────────────────
app.use(helmet({ contentSecurityPolicy: false }));
app.use(cors({ origin: process.env.ALLOWED_ORIGINS?.split(',') || '*' }));
app.use(morgan('combined', { stream: logger.stream }));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Serve frontend static files
app.use(express.static(path.join(__dirname, '../frontend')));

// Rate limiting
const apiLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: process.env.RATE_LIMIT || 100,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many requests — please try again in 15 minutes.' }
});
app.use('/api/', apiLimiter);

// AI endpoint — stricter limit (Gemini API costs)
const aiLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 30,
  message: { error: 'AI rate limit reached — max 30 requests/minute.' }
});
app.use('/api/ai/', aiLimiter);

// ── API ROUTES ─────────────────────────────────────────────────
app.use('/api/ai',         aiRoutes);
app.use('/api/crowd',      crowdRoutes);
app.use('/api/transport',  transportRoutes);
app.use('/api/incidents',  incidentRoutes);
app.use('/api/staff',      staffRoutes);
app.use('/api/eco',        ecoRoutes);
app.use('/api/analytics',  analyticsRoutes);

// Health check
app.get('/api/health', (req, res) => {
  res.json({
    status: 'operational',
    version: '1.0.0',
    platform: 'StadiumIQ — FIFA World Cup 2026',
    timestamp: new Date().toISOString(),
    services: {
      gemini_ai:   process.env.GEMINI_API_KEY ? 'connected' : 'no_key',
      crowd_sim:   'active',
      transport:   'active',
      incidents:   'active',
      websocket:   'active'
    }
  });
});

// Catch-all → serve frontend
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../frontend/index.html'));
});

// ── REAL-TIME WEBSOCKET ────────────────────────────────────────
io.on('connection', (socket) => {
  logger.info(`Client connected: ${socket.id}`);

  // Send initial state
  socket.emit('stadium:state', CrowdSimulator.getFullState());
  socket.emit('transport:state', TransportOptimizer.getFullState());

  // Subscribe to venue updates
  socket.on('subscribe:venue', (venueId) => {
    socket.join(`venue:${venueId}`);
    socket.emit('venue:state', CrowdSimulator.getVenueState(venueId));
    logger.info(`Client ${socket.id} subscribed to venue ${venueId}`);
  });

  // Subscribe to incident updates
  socket.on('subscribe:incidents', () => {
    socket.join('incidents');
  });

  // Report incident via WebSocket
  socket.on('incident:report', async (data) => {
    const incident = await IncidentManager.createIncident(data);
    io.to('incidents').emit('incident:new', incident);
    logger.warn(`Incident reported: ${incident.id} — ${incident.type}`);
  });

  socket.on('disconnect', () => {
    logger.info(`Client disconnected: ${socket.id}`);
  });
});

// ── REAL-TIME DATA BROADCAST ───────────────────────────────────
// Push crowd updates every 10 seconds
setInterval(() => {
  const update = CrowdSimulator.tick();
  io.emit('crowd:update', update);
}, 10000);

// Push transport updates every 15 seconds
setInterval(() => {
  const update = TransportOptimizer.tick();
  io.emit('transport:update', update);
}, 15000);

// Push KPI snapshots every 30 seconds
setInterval(() => {
  io.emit('kpi:snapshot', {
    timestamp: new Date().toISOString(),
    crowd:     CrowdSimulator.getKPIs(),
    transport: TransportOptimizer.getKPIs(),
    incidents: IncidentManager.getKPIs(),
  });
}, 30000);

// ── START SERVER ───────────────────────────────────────────────
server.listen(PORT, () => {
  logger.info(`🏟️  StadiumIQ Backend running on port ${PORT}`);
  logger.info(`🤖 Gemini AI: ${process.env.GEMINI_API_KEY ? 'Connected' : 'No API key — set GEMINI_API_KEY in .env'}`);
  logger.info(`🌐 Frontend: http://localhost:${PORT}`);
  logger.info(`📡 WebSocket: ws://localhost:${PORT}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  logger.info('SIGTERM received — shutting down gracefully');
  server.close(() => {
    logger.info('Server closed');
    process.exit(0);
  });
});

module.exports = { app, io };
