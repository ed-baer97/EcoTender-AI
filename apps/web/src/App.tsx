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
  Menu,
  MenuItem,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Polyline,
  Polygon,
  useMap,
} from "react-leaflet";
import AdminPanel from "./AdminPanel";

function FlyToSelected({ lat, lon }: { lat?: number | null; lon?: number | null }) {
  const map = useMap();
  useEffect(() => {
    if (lat == null || lon == null) return;
    map.flyTo([lat, lon], Math.max(map.getZoom(), 9), { duration: 0.85 });
  }, [lat, lon, map]);
  return null;
}

function InvalidateMapSize({ active }: { active: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (!active) return;
    const id = window.setTimeout(() => map.invalidateSize(), 80);
    return () => window.clearTimeout(id);
  }, [active, map]);
  return null;
}

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
  extras?: Record<string, any>;
};

type ExplainSections = {
  verdict?: string;
  evidence?: string[];
  gaps?: string[];
  recommendation?: string;
};

type Risk = {
  risk_score: number;
  risk_band: string;
  model_risk_score?: number;
  model_risk_band?: string;
  explanation?: string;
  explanation_sections?: ExplainSections;
  reasons?: { code: string; message_ru: string; severity: string }[];
  model_version?: string;
  explanation_meta?: {
    source?: string;
    model?: string;
    evidence_hash?: string;
    prompt_version?: string;
    error?: string;
    confidence?: string;
    conflict?: boolean;
  };
  evidence_summary?: { docs?: number; gaps?: string[]; kv_keys?: number };
  verdicts?: {
    model?: { risk_score?: number; risk_band?: string; summary?: string };
    auditor?: { risk_band?: string; summary?: string; agree_with_model?: boolean | null };
    conflict?: boolean;
    confidence?: string;
  };
};

function parseExplainSections(text?: string, sections?: ExplainSections | null): ExplainSections {
  if (sections?.verdict || (sections?.evidence && sections.evidence.length) || sections?.recommendation) {
    return sections;
  }
  if (!text) return {};
  const parts = text.split(/(?=(?:^|\s)[ABCD]\))/);
  const found: Record<string, string> = {};
  for (const chunk of parts) {
    const m = chunk.trim().match(/^([ABCD])\)\s*([\s\S]*)$/);
    if (m) found[m[1]] = m[2].trim();
  }
  if (!Object.keys(found).length) return { verdict: text };
  const toBullets = (block: string) => {
    const cleaned = block.replace(/^(Подтверждения[^\n:]*|Пробелы[^\n:]*|Evidence|Gaps)\s*:\s*/i, "").trim();
    if (/^[-•\d]/m.test(cleaned) || cleaned.includes("\n")) {
      return cleaned
        .split(/\n+/)
        .map((ln) => ln.replace(/^[-•\d.\)\s]+/, "").trim())
        .filter(Boolean);
    }
    return cleaned
      .split(/(?<=\.)\s+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 6);
  };
  return {
    verdict: found.A?.replace(/^(Вердикт|Verdict)\s*:\s*/i, "").trim(),
    evidence: found.B ? toBullets(found.B) : undefined,
    gaps: found.C ? toBullets(found.C) : undefined,
    recommendation: found.D?.replace(/^(Рекомендация|Recommendation)\s*:\s*/i, "").trim(),
  };
}

function ExplainBlocks({ text, sections }: { text?: string; sections?: ExplainSections }) {
  const s = parseExplainSections(text, sections);
  if (!s.verdict && !(s.evidence || []).length && !s.recommendation) {
    return (
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
        {text}
      </Typography>
    );
  }
  return (
    <Stack spacing={1.5}>
      {s.verdict && (
        <Box>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block">
            A) Вердикт
          </Typography>
          <Typography variant="body2">{s.verdict}</Typography>
        </Box>
      )}
      {(s.evidence || []).length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.5}>
            B) Подтверждения из документов
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 2.2 }}>
            {(s.evidence || []).map((item, i) => (
              <Typography key={i} component="li" variant="body2" sx={{ mb: 0.4 }}>
                {item}
              </Typography>
            ))}
          </Box>
        </Box>
      )}
      {(s.gaps || []).length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.5}>
            C) Пробелы данных
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 2.2 }}>
            {(s.gaps || []).map((item, i) => (
              <Typography key={i} component="li" variant="body2" sx={{ mb: 0.4 }}>
                {item}
              </Typography>
            ))}
          </Box>
        </Box>
      )}
      {s.recommendation && (
        <Box>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block">
            D) Рекомендация
          </Typography>
          <Typography variant="body2">{s.recommendation}</Typography>
        </Box>
      )}
    </Stack>
  );
}

function gosExtras(t?: Tender | null) {
  const gos = (t?.extras as any)?.goszakup || {};
  return {
    filters: (t?.extras as any)?.search_filters || {},
    docs: gos.documents || [],
    tabs: gos.tabs || [],
    lots: gos.lots || [],
    kv: gos.kv || {},
  };
}

/** Direct portal URL for manual verification. */
function portalAnnounceUrl(t?: Tender | null): string | null {
  if (!t) return null;
  const extras = t.extras || {};
  const fromExtras = extras.detail_url || extras.goszakup?.detail_url;
  if (typeof fromExtras === "string" && fromExtras.startsWith("http")) return fromExtras;
  const gid = extras.goszakup_id ?? extras.goszakup?.announce_id;
  if (gid != null && String(gid).match(/^\d+$/)) {
    return `https://goszakup.gov.kz/ru/announce/index/${gid}`;
  }
  const m = String(t.external_id || "").match(/^(\d{5,})/);
  if (m) return `https://goszakup.gov.kz/ru/announce/index/${m[1]}`;
  return null;
}

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
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [coast, setCoast] = useState<[number, number][]>([]);
  const [protectedPolys, setProtectedPolys] = useState<PolyFeature[]>([]);
  const [workPolys, setWorkPolys] = useState<PolyFeature[]>([]);
  const [selected, setSelected] = useState<Tender | null>(null);
  const [risk, setRisk] = useState<Risk | null>(null);
  const [riskBusy, setRiskBusy] = useState(false);
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
  const [mobilePane, setMobilePane] = useState<"list" | "map">("map");
  const [layersAnchor, setLayersAnchor] = useState<null | HTMLElement>(null);
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

  async function openTender(t: Tender, opts?: { force?: boolean }) {
    setSelected(t);
    setRisk(null);
    setContractor(null);
    setError(null);
    if (isMobile) setMobilePane("map");
    const ref = t.id || t.external_id;
    const cached = (t.extras as any)?.llm_explain;
    if (!opts?.force && cached?.text && cached?.risk_score != null) {
      setRisk({
        risk_score: cached.risk_score,
        risk_band: cached.risk_band || t.risk_band || "medium",
        model_risk_score: cached.model_risk_score,
        model_risk_band: cached.model_risk_band,
        explanation: cached.text,
        explanation_sections: cached.sections,
        model_version: undefined,
        explanation_meta: {
          source: "cache",
          model: cached.model,
          evidence_hash: cached.evidence_hash,
          prompt_version: cached.prompt_version,
          confidence: cached.confidence,
          conflict: cached.conflict,
        },
        evidence_summary: cached.evidence_summary,
        verdicts: cached.verdicts,
      });
    }
    setRiskBusy(true);
    try {
      const q = opts?.force ? "?force=true" : "";
      const res = await fetch(`${API}/tenders/${ref}/risk${q}`, { method: "POST" });
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
    } finally {
      setRiskBusy(false);
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
    <Box
      sx={{
        height: { xs: "100dvh", md: "100vh" },
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <Box
        sx={{
          px: { xs: 1.5, sm: 3 },
          py: { xs: 1, sm: 1.5 },
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
          flexShrink: 0,
        }}
      >
        <Stack direction="row" alignItems="center" spacing={{ xs: 0.75, sm: 2 }} flexWrap="wrap" useFlexGap>
          <Typography
            variant={isMobile ? "h6" : "h5"}
            sx={{ letterSpacing: "-0.02em", lineHeight: 1.2, flexShrink: 0 }}
          >
            EcoTender AI
          </Typography>
          {!isMobile && (
            <Typography variant="body2" color="text.secondary">
              Казахстан · Каспийское побережье
            </Typography>
          )}
          {!isMobile && <Chip size="small" label="KZ" color="primary" />}
          {!isMobile &&
            (["critical", "high", "medium", "low"] as const).map((b) => (
              <Chip
                key={b}
                size="small"
                variant="outlined"
                label={`${b}: ${counts[b]}`}
                sx={{ borderColor: bandColor[b], color: bandColor[b] }}
              />
            ))}
          {isMobile && (
            <Chip
              size="small"
              variant="outlined"
              label={`${counts.critical + counts.high} риск`}
              sx={{ borderColor: bandColor.high, color: bandColor.high }}
            />
          )}
          <Box sx={{ flex: 1, minWidth: 8 }} />
          {isMobile ? (
            <>
              <Button size="small" variant="text" onClick={(e) => setLayersAnchor(e.currentTarget)} sx={{ minWidth: 0, px: 1 }}>
                Слои
              </Button>
              <Menu
                anchorEl={layersAnchor}
                open={!!layersAnchor}
                onClose={() => setLayersAnchor(null)}
                anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
                transformOrigin={{ vertical: "top", horizontal: "right" }}
              >
                <MenuItem disableRipple sx={{ py: 0 }}>
                  <FormControlLabel
                    control={<Switch size="small" checked={showGibs} onChange={(_, v) => setShowGibs(v)} />}
                    label="NASA GIBS"
                  />
                </MenuItem>
                <MenuItem disableRipple sx={{ py: 0 }}>
                  <FormControlLabel
                    control={<Switch size="small" checked={showProtected} onChange={(_, v) => setShowProtected(v)} />}
                    label="ООПТ"
                  />
                </MenuItem>
                <MenuItem disableRipple sx={{ py: 0 }}>
                  <FormControlLabel
                    control={<Switch size="small" checked={showWork} onChange={(_, v) => setShowWork(v)} />}
                    label="Полигоны"
                  />
                </MenuItem>
              </Menu>
            </>
          ) : (
            <>
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
            </>
          )}
          {user?.role === "admin" && (
            <Button
              size="small"
              variant="contained"
              color="secondary"
              onClick={() => setView("admin")}
              sx={{ whiteSpace: "nowrap" }}
            >
              {isMobile ? "Админ" : "Кабинет администратора"}
            </Button>
          )}
          {user ? (
            <Chip
              size="small"
              color={user.role === "admin" ? "secondary" : "default"}
              label={isMobile ? user.role : `${user.name} · ${user.role}`}
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
        <Alert severity="warning" sx={{ borderRadius: 0, py: 0.5, flexShrink: 0 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {isMobile && (
        <Box
          sx={{
            px: 1.5,
            py: 1,
            borderBottom: "1px solid",
            borderColor: "divider",
            bgcolor: "background.paper",
            flexShrink: 0,
          }}
        >
          <ToggleButtonGroup
            exclusive
            fullWidth
            size="small"
            value={mobilePane}
            onChange={(_, v) => v && setMobilePane(v)}
          >
            <ToggleButton value="list">Список · {tenders.length}</ToggleButton>
            <ToggleButton value="map">Карта</ToggleButton>
          </ToggleButtonGroup>
        </Box>
      )}

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "360px 1fr" },
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
          position: "relative",
        }}
      >
        <Box
          sx={{
            overflow: "auto",
            borderRight: { md: "1px solid" },
            borderColor: "divider",
            bgcolor: "background.paper",
            display: { xs: mobilePane === "list" ? "block" : "none", md: "block" },
            minHeight: 0,
            WebkitOverflowScrolling: "touch",
            position: { xs: "absolute", md: "relative" },
            inset: { xs: 0, md: "auto" },
            zIndex: { xs: 2, md: "auto" },
          }}
        >
          <Box sx={{ p: 2, position: "sticky", top: 0, bgcolor: "background.paper", zIndex: 1 }}>
            <Typography variant="subtitle2" color="text.secondary">
              Эко-тендеры KZ · {tenders.length}
            </Typography>
            {isMobile && (
              <Stack direction="row" gap={0.5} flexWrap="wrap" mt={1}>
                {(["critical", "high", "medium", "low"] as const).map((b) => (
                  <Chip
                    key={b}
                    size="small"
                    variant="outlined"
                    label={`${b}: ${counts[b]}`}
                    sx={{ borderColor: bandColor[b], color: bandColor[b] }}
                  />
                ))}
              </Stack>
            )}
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
                    secondary={
                      <Box component="span">
                        {`${t.region_name || "KZ"} · risk ${t.risk_score ?? "—"}`}
                        {portalAnnounceUrl(t) ? (
                          <>
                            {" · "}
                            <Box
                              component="a"
                              href={portalAnnounceUrl(t)!}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              sx={{ color: "primary.main" }}
                            >
                              goszakup
                            </Box>
                          </>
                        ) : null}
                      </Box>
                    }
                    primaryTypographyProps={{ fontSize: 14 }}
                    secondaryTypographyProps={{ component: "div" }}
                  />
                </ListItemButton>
              ))}
          </List>
        </Box>

        <Box
          sx={{
            position: { xs: "absolute", md: "relative" },
            inset: { xs: 0, md: "auto" },
            minHeight: 0,
            height: { md: "100%" },
            visibility: { xs: mobilePane === "map" ? "visible" : "hidden", md: "visible" },
            zIndex: { xs: 1, md: "auto" },
          }}
        >
          <MapContainer center={center} zoom={6} style={{ height: "100%", width: "100%" }}>
            <FlyToSelected lat={selected?.lat} lon={selected?.lon} />
            <InvalidateMapSize active={!isMobile || mobilePane === "map"} />
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
                const active = selected?.external_id === t.external_id;
                return (
                  <CircleMarker
                    key={t.external_id}
                    center={[t.lat!, t.lon!]}
                    radius={active ? 14 : t.risk_band === "critical" || t.risk_band === "high" ? 11 : 8}
                    pathOptions={{
                      color,
                      fillColor: color,
                      fillOpacity: active ? 1 : 0.85,
                      weight: active ? 3 : 1,
                    }}
                    eventHandlers={{ click: () => openTender(t) }}
                  >
                    <Popup>
                      {t.title}
                      <br />
                      risk: {t.risk_score} ({t.risk_band})
                      {portalAnnounceUrl(t) ? (
                        <>
                          <br />
                          <a href={portalAnnounceUrl(t)!} target="_blank" rel="noopener noreferrer">
                            goszakup →
                          </a>
                        </>
                      ) : null}
                    </Popup>
                  </CircleMarker>
                );
              })}
          </MapContainer>
        </Box>
      </Box>

      <Drawer
        anchor={isMobile ? "bottom" : "right"}
        open={!!selected}
        onClose={() => setSelected(null)}
        PaperProps={{
          sx: {
            width: { xs: "100%", sm: isMobile ? "100%" : 440 },
            maxHeight: { xs: "88dvh", sm: "100%" },
            borderTopLeftRadius: { xs: 12, sm: 0 },
            borderTopRightRadius: { xs: 12, sm: 0 },
          },
        }}
      >
        {selected && (
          <Box sx={{ p: { xs: 2, sm: 3 }, pb: { xs: "max(16px, env(safe-area-inset-bottom))", sm: 3 }, overflow: "auto" }}>
            {isMobile && (
              <Box sx={{ width: 40, height: 4, borderRadius: 2, bgcolor: "divider", mx: "auto", mb: 1.5 }} />
            )}
            <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1} mb={1}>
              <Typography variant="h6" sx={{ fontSize: { xs: "1.05rem", sm: "1.25rem" }, pr: 1 }}>
                {selected.title}
              </Typography>
              <Button size="small" onClick={() => setSelected(null)} sx={{ flexShrink: 0, minWidth: 0 }}>
                Закрыть
              </Button>
            </Stack>
            <Stack direction="row" gap={1} flexWrap="wrap" mb={1} alignItems="center">
              <Chip size="small" label="KZ" />
              <Chip size="small" label={selected.eco_category || "eco"} variant="outlined" />
              {selected.amount != null && (
                <Chip size="small" label={`${selected.amount.toLocaleString("ru-RU")} ${selected.currency || "KZT"}`} />
              )}
            </Stack>
            {portalAnnounceUrl(selected) && (
              <Typography variant="body2" mb={2}>
                <Box
                  component="a"
                  href={portalAnnounceUrl(selected)!}
                  target="_blank"
                  rel="noopener noreferrer"
                  sx={{ color: "primary.main", wordBreak: "break-all" }}
                >
                  Открыть на goszakup.gov.kz →
                </Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  {selected.external_id}
                </Typography>
              </Typography>
            )}
            <Alert severity="info" sx={{ mb: 2 }}>
              Risk Score — аналитический индикатор, не юридическое обвинение.
            </Alert>

            {risk ? (
              <Stack spacing={1.5} mb={2}>
                <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
                  <Typography variant="h4" sx={{ color: bandColor[risk.risk_band] || "text.primary", fontSize: { xs: "1.75rem", sm: "2.125rem" } }}>
                    {risk.risk_score}
                    <Typography component="span" variant="body2" color="text.secondary">
                      {" "}
                      / 100 · {risk.risk_band}
                    </Typography>
                  </Typography>
                  {(risk.verdicts?.confidence || risk.explanation_meta?.confidence) === "low" && (
                    <Chip size="small" color="warning" label="low confidence" />
                  )}
                  {(risk.verdicts?.conflict || risk.explanation_meta?.conflict) && (
                    <Chip size="small" color="error" variant="outlined" label="расхождение слоёв" />
                  )}
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={riskBusy || !selected}
                    onClick={() => selected && openTender(selected, { force: true })}
                  >
                    {riskBusy ? "Считаем…" : "Пересчитать"}
                  </Button>
                </Stack>

                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Chip
                    size="small"
                    variant="outlined"
                    sx={{
                      borderColor: bandColor[risk.verdicts?.model?.risk_band || risk.model_risk_band || risk.risk_band] || undefined,
                      height: "auto",
                      py: 0.6,
                      "& .MuiChip-label": { whiteSpace: "normal", maxWidth: { xs: "100%", sm: 200 } },
                    }}
                    label={`Модель: ${risk.verdicts?.model?.risk_score ?? risk.model_risk_score ?? risk.risk_score} · ${
                      risk.verdicts?.model?.risk_band || risk.model_risk_band || risk.risk_band
                    }`}
                  />
                  <Chip
                    size="small"
                    variant="outlined"
                    color={risk.verdicts?.conflict ? "warning" : "default"}
                    sx={{ height: "auto", py: 0.6, "& .MuiChip-label": { whiteSpace: "normal", maxWidth: { xs: "100%", sm: 220 } } }}
                    label={`Аудитор: ${risk.verdicts?.auditor?.risk_band || risk.risk_band}${
                      risk.verdicts?.auditor?.summary
                        ? ` — ${String(risk.verdicts.auditor.summary).slice(0, 90)}`
                        : ""
                    }`}
                  />
                </Stack>

                {(risk.verdicts?.conflict || risk.explanation_meta?.conflict) && (
                  <Alert severity="warning" sx={{ py: 0.5 }}>
                    Модель и аудитор по документам расходятся. Показанный score скорректирован (low confidence).
                  </Alert>
                )}

                <ExplainBlocks text={risk.explanation} sections={risk.explanation_sections} />
                <Typography variant="caption" color="text.secondary">
                  docs: {gosExtras(selected).docs.length} · tabs: {gosExtras(selected).tabs.length} · lots:{" "}
                  {gosExtras(selected).lots.length}
                  {risk.evidence_summary?.docs != null ? ` · excerpts: ${risk.evidence_summary.docs}` : ""}
                  {risk.explanation_meta?.source ? ` · explain: ${risk.explanation_meta.source}` : ""}
                </Typography>
                {Object.keys(gosExtras(selected).kv).length > 0 && (
                  <Box sx={{ bgcolor: "action.hover", p: 1.2, borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
                      Общие сведения
                    </Typography>
                    {Object.entries(gosExtras(selected).kv)
                      .slice(0, 8)
                      .map(([k, v]) => (
                        <Typography key={k} variant="caption" display="block">
                          {k}: {String(v)}
                        </Typography>
                      ))}
                  </Box>
                )}
                {gosExtras(selected).docs.length > 0 && (
                  <Box>
                    <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
                      Документы / спецификация ({gosExtras(selected).docs.length})
                    </Typography>
                    <Box sx={{ maxHeight: 220, overflow: "auto", bgcolor: "action.hover", p: 1, borderRadius: 1 }}>
                      {Object.entries(
                        gosExtras(selected).docs.reduce((acc: Record<string, any[]>, d: any) => {
                          const key = d.group_name || d.kind || "Документы";
                          (acc[key] ||= []).push(d);
                          return acc;
                        }, {})
                      ).map(([group, docs]) => (
                        <Box key={group} mb={1}>
                          <Typography variant="caption" fontWeight={600} display="block">
                            {group} · {(docs as any[]).length}
                          </Typography>
                          {(docs as any[]).map((d: any, idx: number) => (
                            <Typography
                              key={`${d.url || d.name}-${idx}`}
                              variant="caption"
                              display="block"
                              sx={{ wordBreak: "break-all", pl: 1 }}
                            >
                              {d.lot_number ? `[${d.lot_number}] ` : ""}
                              {d.url ? (
                                <Box
                                  component="a"
                                  href={d.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  sx={{ color: "primary.main" }}
                                >
                                  {d.name || d.url}
                                </Box>
                              ) : (
                                d.name
                              )}
                            </Typography>
                          ))}
                        </Box>
                      ))}
                    </Box>
                  </Box>
                )}
                {Object.keys(gosExtras(selected).filters).length > 0 && (
                  <Typography variant="caption" color="text.secondary" sx={{ wordBreak: "break-all" }}>
                    search: {JSON.stringify(gosExtras(selected).filters)}
                  </Typography>
                )}
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
                {riskBusy ? "Слой 1 (CatBoost) → слой 2 (Qwen)…" : "Расчёт риска…"}
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

      <Dialog open={loginOpen} onClose={() => setLoginOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Вход</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
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
