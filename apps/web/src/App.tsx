import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControlLabel,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Polyline,
  Polygon,
} from "react-leaflet";
import AdminPanel from "./AdminPanel";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
const GIBS_URL =
  "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";
const TOKEN_KEY = "ecotender_token";

type Tender = {
  id?: string;
  external_id: string;
  title: string;
  country_code: string;
  eco_category?: string;
  region_name?: string;
  amount?: number;
  currency?: string;
  lat?: number;
  lon?: number;
  participants_count?: number;
  risk_score?: number;
  risk_band?: string;
  winner_name?: string;
  contractor_wins_2y?: number;
  contractor_win_rate?: number;
  amendments_count?: number;
  amendment_amount_ratio?: number;
  market_amount_est?: number;
};

type Risk = {
  risk_score: number;
  risk_band: string;
  explanation?: string;
  reasons?: { code: string; message_ru: string; severity: string }[];
  model_version?: string;
  explanation_meta?: { source?: string; model?: string };
};

type Contractor = {
  name: string;
  tenders_count: number;
  wins_2y: number;
  win_rate: number;
  avg_risk_score: number | null;
  max_risk_score: number | null;
  high_risk_count: number;
  tenders?: { external_id: string; title: string; risk_score?: number; risk_band?: string }[];
};

type User = { email: string; role: string; name: string };

type PolyFeature = {
  positions: [number, number][];
  name: string;
  kind: "protected" | "work";
  color: string;
};

const bandColor: Record<string, string> = {
  low: "#2E7D32",
  medium: "#F9A825",
  high: "#EF6C00",
  critical: "#C62828",
};

export default function App() {
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [coast, setCoast] = useState<[number, number][]>([]);
  const [protectedPolys, setProtectedPolys] = useState<PolyFeature[]>([]);
  const [workPolys, setWorkPolys] = useState<PolyFeature[]>([]);
  const [selected, setSelected] = useState<Tender | null>(null);
  const [risk, setRisk] = useState<Risk | null>(null);
  const [contractor, setContractor] = useState<Contractor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showGibs, setShowGibs] = useState(false);
  const [showProtected, setShowProtected] = useState(true);
  const [showWork, setShowWork] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [email, setEmail] = useState("analyst@ecotender.kz");
  const [password, setPassword] = useState("analyst123");
  const [view, setView] = useState<"map" | "admin">("map");
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));

  useEffect(() => {
    if (!token) return;
    fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => {
        if (u) setUser(u);
        else {
          localStorage.removeItem(TOKEN_KEY);
          setToken(null);
        }
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
      });
  }, [token]);

  useEffect(() => {
    (async () => {
      try {
        const layers = "tenders,coastline,protected,work_polygons";
        const [tRes, mRes] = await Promise.all([
          fetch(`${API}/tenders?country=KZ&size=100`),
          fetch(`${API}/map/features?bbox=49,42,55,48.5&layers=${layers}`),
        ]);
        if (!tRes.ok) throw new Error("tenders API unavailable");
        const tJson = await tRes.json();
        setTenders((tJson.items || []).filter((t: Tender) => t.country_code === "KZ"));
        if (mRes.ok) {
          const geo = await mRes.json();
          const features = geo.features || [];
          const line = features.find((f: any) => f.properties?.kind === "coastline");
          if (line) {
            setCoast(line.geometry.coordinates.map((c: number[]) => [c[1], c[0]] as [number, number]));
          }
          setProtectedPolys(
            features
              .filter((f: any) => f.properties?.kind === "protected")
              .map((f: any) => ({
                positions: f.geometry.coordinates[0].map((c: number[]) => [c[1], c[0]] as [number, number]),
                name: f.properties.name,
                kind: "protected" as const,
                color: "#2E7D32",
              }))
          );
          setWorkPolys(
            features
              .filter((f: any) => f.properties?.kind === "work_polygon")
              .map((f: any) => ({
                positions: f.geometry.coordinates[0].map((c: number[]) => [c[1], c[0]] as [number, number]),
                name: f.properties.title || f.properties.external_id,
                kind: "work" as const,
                color: bandColor[f.properties.risk_band || "high"] || "#EF6C00",
              }))
          );
        }
      } catch {
        setError("API недоступен. Запустите docker compose up.");
      }
    })();
  }, []);

  const center = useMemo<[number, number]>(() => [44.8, 51.8], []);
  const counts = useMemo(() => {
    const c = { low: 0, medium: 0, high: 0, critical: 0 };
    for (const t of tenders) {
      const b = (t.risk_band || "low") as keyof typeof c;
      if (b in c) c[b] += 1;
    }
    return c;
  }, [tenders]);

  async function openTender(t: Tender) {
    setSelected(t);
    setRisk(null);
    setContractor(null);
    setError(null);
    const ref = t.id || t.external_id;
    try {
      const res = await fetch(`${API}/tenders/${ref}/risk`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setRisk(data.risk);
        if (data.tender) setSelected({ ...t, ...data.tender });
      }
      if (t.winner_name) {
        const cRes = await fetch(`${API}/contractors/${encodeURIComponent(t.winner_name)}`);
        if (cRes.ok) setContractor(await cRes.json());
      }
    } catch {
      setError("Не удалось рассчитать Risk Score");
    }
  }

  async function doLogin() {
    const res = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      setError("Неверный логин/пароль");
      return;
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    setLoginOpen(false);
    setError(null);
    if (data.user?.role === "admin") setView("admin");
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
    setView("map");
  }

  if (view === "admin" && user?.role === "admin" && token) {
    return <AdminPanel token={token} user={user} onBack={() => setView("map")} />;
  }

  return (
    <Box sx={{ height: "100vh", display: "grid", gridTemplateRows: "auto 1fr" }}>
      <Box sx={{ px: 3, py: 1.5, borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
        <Stack direction="row" alignItems="center" spacing={2} flexWrap="wrap">
          <Typography variant="h5" sx={{ letterSpacing: "-0.02em" }}>
            EcoTender AI
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Казахстан · Каспийское побережье
          </Typography>
          <Chip size="small" label="KZ" color="primary" />
          {(["critical", "high", "medium", "low"] as const).map((b) => (
            <Chip
              key={b}
              size="small"
              variant="outlined"
              label={`${b}: ${counts[b]}`}
              sx={{ borderColor: bandColor[b], color: bandColor[b] }}
            />
          ))}
          <Box sx={{ flex: 1 }} />
          <FormControlLabel
            control={<Switch size="small" checked={showGibs} onChange={(_, v) => setShowGibs(v)} />}
            label={<Typography variant="caption">NASA GIBS</Typography>}
          />
          <FormControlLabel
            control={<Switch size="small" checked={showProtected} onChange={(_, v) => setShowProtected(v)} />}
            label={<Typography variant="caption">ООПТ</Typography>}
          />
          <FormControlLabel
            control={<Switch size="small" checked={showWork} onChange={(_, v) => setShowWork(v)} />}
            label={<Typography variant="caption">Полигоны</Typography>}
          />
          {user?.role === "admin" && (
            <Button size="small" variant="contained" color="secondary" onClick={() => setView("admin")}>
              Админка
            </Button>
          )}
          {user ? (
            <Chip
              size="small"
              color={user.role === "admin" ? "secondary" : "default"}
              label={`${user.name} · ${user.role}`}
              onDelete={logout}
            />
          ) : (
            <Button size="small" variant="outlined" onClick={() => setLoginOpen(true)}>
              Войти
            </Button>
          )}
        </Stack>
      </Box>

      {error && (
        <Alert severity="warning" sx={{ borderRadius: 0 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "360px 1fr" }, minHeight: 0 }}>
        <Box sx={{ overflow: "auto", borderRight: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
          <Box sx={{ p: 2 }}>
            <Typography variant="subtitle2" color="text.secondary">
              Эко-тендеры KZ · {tenders.length}
            </Typography>
          </Box>
          <List dense>
            {[...tenders]
              .sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))
              .map((t) => (
                <ListItemButton key={t.external_id} selected={selected?.external_id === t.external_id} onClick={() => openTender(t)}>
                  <Box
                    sx={{
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      bgcolor: bandColor[t.risk_band || "low"],
                      mr: 1.5,
                      flexShrink: 0,
                    }}
                  />
                  <ListItemText
                    primary={t.title}
                    secondary={`${t.region_name || "KZ"} · risk ${t.risk_score ?? "—"}`}
                    primaryTypographyProps={{ fontSize: 14 }}
                  />
                </ListItemButton>
              ))}
          </List>
        </Box>

        <Box sx={{ position: "relative", minHeight: 420 }}>
          <MapContainer center={center} zoom={6} style={{ height: "100%", width: "100%" }}>
            <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {showGibs && <TileLayer url={GIBS_URL} opacity={0.55} attribution="NASA GIBS" maxNativeZoom={8} />}
            {coast.length > 0 && <Polyline positions={coast} pathOptions={{ color: "#1B4965", weight: 2 }} />}
            {showProtected &&
              protectedPolys.map((p) => (
                <Polygon
                  key={p.name}
                  positions={p.positions}
                  pathOptions={{ color: p.color, fillColor: p.color, fillOpacity: 0.18, weight: 2 }}
                >
                  <Popup>ООПТ: {p.name}</Popup>
                </Polygon>
              ))}
            {showWork &&
              workPolys.map((p) => (
                <Polygon
                  key={p.name}
                  positions={p.positions}
                  pathOptions={{ color: p.color, fillColor: p.color, fillOpacity: 0.25, weight: 1, dashArray: "4 4" }}
                >
                  <Popup>Полигон работ: {p.name}</Popup>
                </Polygon>
              ))}
            {tenders
              .filter((t) => t.lat && t.lon)
              .map((t) => {
                const color = bandColor[t.risk_band || "low"];
                return (
                  <CircleMarker
                    key={t.external_id}
                    center={[t.lat!, t.lon!]}
                    radius={t.risk_band === "critical" || t.risk_band === "high" ? 11 : 8}
                    pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: 1 }}
                    eventHandlers={{ click: () => openTender(t) }}
                  >
                    <Popup>
                      {t.title}
                      <br />
                      risk: {t.risk_score} ({t.risk_band})
                    </Popup>
                  </CircleMarker>
                );
              })}
          </MapContainer>
        </Box>
      </Box>

      <Drawer anchor="right" open={!!selected} onClose={() => setSelected(null)} PaperProps={{ sx: { width: { xs: "100%", sm: 440 } } }}>
        {selected && (
          <Box sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              {selected.title}
            </Typography>
            <Stack direction="row" gap={1} flexWrap="wrap" mb={2}>
              <Chip size="small" label="KZ" />
              <Chip size="small" label={selected.eco_category || "eco"} variant="outlined" />
              {selected.amount != null && (
                <Chip size="small" label={`${selected.amount.toLocaleString("ru-RU")} ${selected.currency || "KZT"}`} />
              )}
            </Stack>
            <Alert severity="info" sx={{ mb: 2 }}>
              Risk Score — аналитический индикатор, не юридическое обвинение.
            </Alert>

            {risk ? (
              <Stack spacing={1.5} mb={2}>
                <Typography variant="h4" sx={{ color: bandColor[risk.risk_band] || "text.primary" }}>
                  {risk.risk_score}
                  <Typography component="span" variant="body2" color="text.secondary">
                    {" "}
                    / 100 · {risk.risk_band}
                  </Typography>
                </Typography>
                <Typography variant="body2">{risk.explanation}</Typography>
                <Divider />
                {(risk.reasons || []).map((r) => (
                  <Typography key={r.code} variant="body2">
                    • {r.message_ru}
                  </Typography>
                ))}
                <Typography variant="caption" color="text.secondary">
                  model: {risk.model_version}
                  {risk.explanation_meta?.source ? ` · explain: ${risk.explanation_meta.source}` : ""}
                </Typography>
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary" mb={2}>
                Расчёт риска…
              </Typography>
            )}

            {contractor && (
              <>
                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle1" gutterBottom>
                  Подрядчик
                </Typography>
                <Typography variant="body1" fontWeight={600}>
                  {contractor.name}
                </Typography>
                <Stack direction="row" gap={1} flexWrap="wrap" mt={1} mb={1}>
                  <Chip size="small" label={`побед 2г: ${contractor.wins_2y}`} />
                  <Chip size="small" label={`win rate: ${(contractor.win_rate * 100).toFixed(0)}%`} />
                  <Chip size="small" label={`тендеров: ${contractor.tenders_count}`} />
                  <Chip
                    size="small"
                    color={contractor.high_risk_count > 0 ? "warning" : "default"}
                    label={`high/critical: ${contractor.high_risk_count}`}
                  />
                  {contractor.avg_risk_score != null && (
                    <Chip size="small" label={`ср. risk: ${contractor.avg_risk_score}`} />
                  )}
                </Stack>
                {(contractor.tenders || []).slice(0, 4).map((t) => (
                  <Typography key={t.external_id} variant="caption" display="block" color="text.secondary">
                    · {t.external_id}: {t.risk_score} ({t.risk_band})
                  </Typography>
                ))}
                {!user && (
                  <Alert severity="warning" sx={{ mt: 2 }}>
                    Войдите как analyst, чтобы экспортировать карточку аудита.
                  </Alert>
                )}
                {user && (user.role === "analyst" || user.role === "admin") && (
                  <Alert severity="success" sx={{ mt: 2 }}>
                    Роль {user.role}: доступен расширенный просмотр подрядчика.
                  </Alert>
                )}
              </>
            )}
          </Box>
        )}
      </Drawer>

      <Dialog open={loginOpen} onClose={() => setLoginOpen(false)}>
        <DialogTitle>Вход</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1, minWidth: 280 }}>
            <TextField label="Email" value={email} onChange={(e) => setEmail(e.target.value)} fullWidth size="small" />
            <TextField
              label="Пароль"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              fullWidth
              size="small"
            />
            <Typography variant="caption" color="text.secondary">
              analyst@ecotender.kz / analyst123 · admin@ecotender.kz / admin123
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLoginOpen(false)}>Отмена</Button>
          <Button variant="contained" onClick={doLogin}>
            Войти
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
