import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Drawer,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export type AdminTender = {
  id: string;
  external_id: string;
  title: string;
  description?: string | null;
  country_code: string;
  source_code: string;
  customer_name?: string | null;
  customer_external_id?: string | null;
  amount?: number | null;
  currency?: string | null;
  region_code?: string | null;
  region_name?: string | null;
  eco_category?: string | null;
  procurement_method?: string | null;
  participants_count?: number | null;
  area_sq_m?: number | null;
  duration_days?: number | null;
  winner_name?: string | null;
  amendments_count?: number | null;
  amendment_amount_ratio?: number | null;
  market_amount_est?: number | null;
  contractor_wins_2y?: number | null;
  contractor_win_rate?: number | null;
  risk_score?: number | null;
  risk_band?: string | null;
  lat?: number | null;
  lon?: number | null;
  published_at?: string | null;
  deadline_at?: string | null;
  ingested_at?: string | null;
  extras?: Record<string, unknown>;
};

const bandColor: Record<string, "success" | "warning" | "error" | "default"> = {
  low: "success",
  medium: "warning",
  high: "warning",
  critical: "error",
};

const SOURCE_OPTIONS = [
  { value: "", label: "Все источники" },
  { value: "FIXTURES_CASPIAN", label: "Fixtures (демо)" },
  { value: "KZ_GOSZAKUP_PLAYWRIGHT", label: "goszakup Playwright" },
  { value: "KZ_GOSZAKUP_OWS_V3", label: "goszakup OWS v3" },
];

function fmtMoney(amount?: number | null, currency = "KZT") {
  if (amount == null) return "—";
  return new Intl.NumberFormat("ru-KZ", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
}

function fmtDate(iso?: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru-KZ");
  } catch {
    return iso;
  }
}

function fmtPct(v?: number | null) {
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function asGos(row?: AdminTender | null) {
  const gos = (row?.extras as any)?.goszakup || {};
  return {
    filters: (row?.extras as any)?.search_filters || {},
    keywords: (row?.extras as any)?.matched_keywords || [],
    tabs: gos.tabs || [],
    documents: gos.documents || [],
    lots: gos.lots || [],
    bidders: gos.bidders || [],
    protocols: gos.protocols || [],
    contracts: gos.contracts || [],
    storedAssets: gos.stored_assets || [],
    stats: gos.raw_tab_stats || {},
    kv: gos.kv || {},
    overview: gos.overview_tables || [],
  };
}

function portalAnnounceUrl(row?: AdminTender | null): string | null {
  if (!row) return null;
  const extras = (row.extras || {}) as any;
  const direct = extras.detail_url || extras.goszakup?.detail_url;
  if (typeof direct === "string" && direct.startsWith("http")) return direct;
  const gid = extras.goszakup_id;
  if (gid != null && String(gid).match(/^\d+$/)) {
    return `https://goszakup.gov.kz/ru/announce/index/${gid}`;
  }
  const m = String(row.external_id || "").match(/^(\d{5,})/);
  if (m) return `https://goszakup.gov.kz/ru/announce/index/${m[1]}`;
  return null;
}

type Props = {
  token: string;
  onRunGoszakup?: () => void;
  busy?: boolean;
};

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 1, py: 0.75 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ wordBreak: "break-word" }}>
        {value ?? "—"}
      </Typography>
    </Box>
  );
}

export default function AdminTenders({ token, onRunGoszakup, busy = false }: Props) {
  const [items, setItems] = useState<AdminTender[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [qInput, setQInput] = useState("");
  const [country, setCountry] = useState("KZ");
  const [sourceCode, setSourceCode] = useState("");
  const [selected, setSelected] = useState<AdminTender | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: String(page + 1),
        size: String(rowsPerPage),
      });
      if (country) params.set("country", country);
      if (sourceCode) params.set("source_code", sourceCode);
      if (q.trim()) params.set("q", q.trim());

      const res = await fetch(`${API}/tenders?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Не удалось загрузить тендеры");
      const data = await res.json();
      setItems(data.items || []);
      setTotal(data.total ?? 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, [token, page, rowsPerPage, country, sourceCode, q]);

  useEffect(() => {
    load();
  }, [load]);

  async function openDetail(row: AdminTender) {
    setSelected(row);
    setDetailLoading(true);
    try {
      const res = await fetch(`${API}/tenders/${encodeURIComponent(row.external_id)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const full = await res.json();
        setSelected(full);
      }
    } catch {
      /* keep list row data */
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <Box>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} mb={2} flexWrap="wrap" alignItems="center">
        <Chip label={`Всего в БД: ${total}`} color="primary" variant="outlined" />
        {onRunGoszakup && (
          <Button size="small" variant="contained" onClick={onRunGoszakup} disabled={busy}>
            Запустить goszakup crawl
          </Button>
        )}
        <TextField
          size="small"
          label="Поиск по названию"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setPage(0);
              setQ(qInput);
            }
          }}
          sx={{ minWidth: 200 }}
        />
        <FormControl size="small" sx={{ minWidth: 100 }}>
          <InputLabel>Страна</InputLabel>
          <Select
            label="Страна"
            value={country}
            onChange={(e) => {
              setPage(0);
              setCountry(e.target.value);
            }}
          >
            <MenuItem value="">Все</MenuItem>
            <MenuItem value="KZ">KZ</MenuItem>
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel>Источник</InputLabel>
          <Select
            label="Источник"
            value={sourceCode}
            onChange={(e) => {
              setPage(0);
              setSourceCode(e.target.value);
            }}
          >
            {SOURCE_OPTIONS.map((o) => (
              <MenuItem key={o.value || "all"} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <TableContainer sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Название</TableCell>
              <TableCell>Источник</TableCell>
              <TableCell>Регион</TableCell>
              <TableCell align="right">Сумма</TableCell>
              <TableCell>Risk</TableCell>
              <TableCell>Загружен</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading && items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                  <CircularProgress size={28} />
                </TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 3 }}>
                  <Typography color="text.secondary">Нет записей</Typography>
                </TableCell>
              </TableRow>
            ) : (
              items.map((row) => (
                <TableRow
                  key={row.id || row.external_id}
                  hover
                  sx={{ cursor: "pointer" }}
                  onClick={() => openDetail(row)}
                  selected={selected?.external_id === row.external_id}
                >
                  <TableCell sx={{ whiteSpace: "nowrap", fontFamily: "monospace", fontSize: 12 }}>
                    {row.external_id}
                    {portalAnnounceUrl(row) && (
                      <Box
                        component="a"
                        href={portalAnnounceUrl(row)!}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        sx={{ display: "block", color: "primary.main", fontSize: 11, mt: 0.3 }}
                      >
                        открыть →
                      </Box>
                    )}
                  </TableCell>
                  <TableCell sx={{ maxWidth: 320 }}>
                    <Typography variant="body2" noWrap title={row.title}>
                      {row.title}
                    </Typography>
                    {row.customer_name && (
                      <Typography variant="caption" color="text.secondary" noWrap display="block">
                        {row.customer_name}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={row.source_code} variant="outlined" sx={{ maxWidth: 140 }} />
                  </TableCell>
                  <TableCell>{row.region_name || row.region_code || "—"}</TableCell>
                  <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                    {fmtMoney(row.amount, row.currency || "KZT")}
                  </TableCell>
                  <TableCell>
                    {row.risk_band ? (
                      <Chip
                        size="small"
                        label={row.risk_score != null ? `${row.risk_score.toFixed(0)}` : row.risk_band}
                        color={bandColor[row.risk_band] || "default"}
                      />
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap", fontSize: 12 }}>
                    {fmtDate(row.ingested_at)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <TablePagination
        component="div"
        count={total}
        page={page}
        onPageChange={(_, p) => setPage(p)}
        rowsPerPage={rowsPerPage}
        onRowsPerPageChange={(e) => {
          setRowsPerPage(parseInt(e.target.value, 10));
          setPage(0);
        }}
        rowsPerPageOptions={[10, 25, 50, 100]}
        labelRowsPerPage="На странице"
      />

      <Drawer
        anchor="right"
        open={!!selected}
        onClose={() => setSelected(null)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, p: 3 } }}
      >
        {selected && (
          <Stack spacing={2}>
            <Typography variant="h6" fontWeight={600}>
              {selected.title}
            </Typography>
            <Chip size="small" label={selected.external_id} sx={{ alignSelf: "flex-start" }} />
            {portalAnnounceUrl(selected) && (
              <DetailRow
                label="Ссылка goszakup"
                value={
                  <Box
                    component="a"
                    href={portalAnnounceUrl(selected)!}
                    target="_blank"
                    rel="noopener noreferrer"
                    sx={{ color: "primary.main", wordBreak: "break-all" }}
                  >
                    {portalAnnounceUrl(selected)}
                  </Box>
                }
              />
            )}
            {detailLoading && <CircularProgress size={24} />}

            <Typography variant="subtitle2" color="primary">
              Основное
            </Typography>
            <DetailRow label="UUID" value={<span style={{ fontFamily: "monospace", fontSize: 11 }}>{selected.id}</span>} />
            <DetailRow label="Страна" value={selected.country_code} />
            <DetailRow label="Источник" value={selected.source_code} />
            <DetailRow label="Эко-категория" value={selected.eco_category} />
            <DetailRow label="Способ закупки" value={selected.procurement_method} />
            <DetailRow label="Заказчик" value={selected.customer_name} />
            <DetailRow label="БИН заказчика" value={selected.customer_external_id} />
            <DetailRow label="Описание" value={selected.description} />

            <Typography variant="subtitle2" color="primary">
              Финансы и риск
            </Typography>
            <DetailRow label="Сумма" value={fmtMoney(selected.amount, selected.currency || "KZT")} />
            <DetailRow label="Рынок (оценка)" value={fmtMoney(selected.market_amount_est, selected.currency || "KZT")} />
            <DetailRow label="Risk Score" value={selected.risk_score?.toFixed(1)} />
            <DetailRow
              label="Risk band"
              value={
                selected.risk_band ? (
                  <Chip size="small" label={selected.risk_band} color={bandColor[selected.risk_band] || "default"} />
                ) : (
                  "—"
                )
              }
            />
            <DetailRow label="Участников" value={selected.participants_count} />
            <DetailRow label="Доп. соглашений" value={selected.amendments_count} />
            <DetailRow label="Доля доп. суммы" value={fmtPct(selected.amendment_amount_ratio)} />

            <Typography variant="subtitle2" color="primary">
              География и сроки
            </Typography>
            <DetailRow label="Регион" value={`${selected.region_name || ""} (${selected.region_code || "—"})`} />
            <DetailRow label="Координаты" value={selected.lat != null ? `${selected.lat}, ${selected.lon}` : "—"} />
            <DetailRow label="Площадь, м²" value={selected.area_sq_m?.toLocaleString("ru-KZ")} />
            <DetailRow label="Срок, дней" value={selected.duration_days} />
            <DetailRow label="Публикация" value={fmtDate(selected.published_at)} />
            <DetailRow label="Дедлайн" value={fmtDate(selected.deadline_at)} />
            <DetailRow label="Загружен в БД" value={fmtDate(selected.ingested_at)} />

            <Typography variant="subtitle2" color="primary">
              Подрядчик
            </Typography>
            <DetailRow label="Победитель" value={selected.winner_name} />
            <DetailRow label="Побед за 2 года" value={selected.contractor_wins_2y} />
            <DetailRow label="Win rate" value={fmtPct(selected.contractor_win_rate)} />

            <Typography variant="subtitle2" color="primary">
              Goszakup crawl
            </Typography>
            <DetailRow
              label="Общие сведения"
              value={
                Object.keys(asGos(selected).kv).length ? (
                  <Stack spacing={0.4}>
                    {Object.entries(asGos(selected).kv)
                      .slice(0, 12)
                      .map(([k, v]) => (
                        <Typography key={k} variant="caption">
                          <strong>{k}:</strong> {String(v)}
                        </Typography>
                      ))}
                  </Stack>
                ) : asGos(selected).overview.length ? (
                  <Stack spacing={0.4}>
                    {asGos(selected).overview[0].rows?.slice(0, 12).map((r: any) => (
                      <Typography key={r.label} variant="caption">
                        <strong>{r.label}:</strong> {r.value}
                      </Typography>
                    ))}
                  </Stack>
                ) : (
                  "—"
                )
              }
            />
            <DetailRow label="Фильтры поиска" value={JSON.stringify(asGos(selected).filters || {})} />
            <DetailRow label="Matched keywords" value={(asGos(selected).keywords || []).join(", ") || "—"} />
            <DetailRow
              label="Статистика"
              value={`tabs=${asGos(selected).stats.tabs_count || 0}, docs=${asGos(selected).stats.documents_count || 0}, lots=${asGos(selected).stats.lots_count || 0}, specs=${asGos(selected).stats.spec_docs_count || 0}`}
            />
            <DetailRow
              label="Вкладки"
              value={
                asGos(selected).tabs.length ? (
                  <Stack spacing={0.5}>
                    {asGos(selected).tabs.slice(0, 8).map((t: any) => (
                      <Typography key={t.slug || t.name} variant="caption">
                        {t.name} ({t.html_len || 0} bytes)
                      </Typography>
                    ))}
                  </Stack>
                ) : (
                  "—"
                )
              }
            />
            <DetailRow
              label="Документы / ТС"
              value={
                asGos(selected).documents.length ? (
                  <Box sx={{ maxHeight: 280, overflow: "auto" }}>
                    <Stack spacing={1}>
                      {Object.entries(
                        asGos(selected).documents.reduce((acc: Record<string, any[]>, d: any) => {
                          const key = d.group_name || d.kind || "Документы";
                          (acc[key] ||= []).push(d);
                          return acc;
                        }, {})
                      ).map(([group, docs]) => (
                        <Box key={group}>
                          <Typography variant="caption" fontWeight={600} display="block">
                            {group} ({(docs as any[]).length})
                          </Typography>
                          {(docs as any[]).map((d: any, idx: number) => (
                            <Typography key={`${d.url}-${idx}`} variant="caption" display="block" sx={{ wordBreak: "break-all", pl: 1 }}>
                              {d.lot_number ? `лот ${d.lot_number}: ` : ""}
                              {d.url ? (
                                <Box component="a" href={d.url} target="_blank" rel="noopener noreferrer" sx={{ color: "primary.main" }}>
                                  {d.name || d.url}
                                </Box>
                              ) : (
                                d.name || "—"
                              )}
                              {d.size ? ` · ${Math.round(d.size / 1024)}KB` : ""}
                              {d.object_key ? ` -> ${d.object_key}` : d.download_error ? ` (err: ${d.download_error})` : ""}
                            </Typography>
                          ))}
                        </Box>
                      ))}
                    </Stack>
                  </Box>
                ) : (
                  "—"
                )
              }
            />
            <DetailRow
              label="Лоты"
              value={
                asGos(selected).lots.length ? (
                  <Stack spacing={0.5}>
                    {asGos(selected).lots.slice(0, 6).map((lot: any, idx: number) => (
                      <Typography key={`${lot.name}-${idx}`} variant="caption">
                        {lot.lot_number ? `${lot.lot_number}: ` : ""}
                        {lot.name} {lot.amount != null ? `· ${fmtMoney(lot.amount, selected.currency || "KZT")}` : ""}
                      </Typography>
                    ))}
                  </Stack>
                ) : (
                  "—"
                )
              }
            />
            <DetailRow
              label="Участники/протоколы"
              value={`bidders=${asGos(selected).bidders.length || 0}, protocols=${asGos(selected).protocols.length || 0}, contracts=${asGos(selected).contracts.length || 0}`}
            />

            {selected.extras && Object.keys(selected.extras).length > 0 && (
              <>
                <Typography variant="subtitle2" color="primary">
                  Extras (парсер)
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    fontSize: 11,
                    bgcolor: "action.hover",
                    p: 1.5,
                    borderRadius: 1,
                    overflow: "auto",
                    maxHeight: 200,
                  }}
                >
                  {JSON.stringify(selected.extras, null, 2)}
                </Box>
              </>
            )}
          </Stack>
        )}
      </Drawer>
    </Box>
  );
}
